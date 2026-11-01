#!/usr/bin/env python3
"""Матриця Hotspots: статична складність (radon JSON) + Churn Rate (git log).

Запускати з КОРЕНЯ репозиторію (радон і git мають давати однакові відносні шляхи):

    radon cc -s -j . > reports/radon-cc.json
    python tools/hotspots.py --cc reports/radon-cc.json --out reports

Метрика складності файлу = максимальна цикломатична складність серед його
функцій/методів (для файлів без функцій -- складність класу).
Категорії (CC > cc-threshold вважається високою; churn >= churn-threshold -- високим):
    Hotspot   (червона)  : висока складність + висока мінливість
    Sleeping  (жовта)    : висока складність + низька мінливість
    Active    (зелена)   : низька складність + висока мінливість
    Stable    (сіра)     : низька складність + низька мінливість
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter

CATEGORIES = {
    (True, True): "Hotspot",
    (True, False): "Sleeping",
    (False, True): "Active",
    (False, False): "Stable",
}
ORDER = {"Hotspot": 0, "Sleeping": 1, "Active": 2, "Stable": 3}


def norm(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


def collect_cc(radon_json: str) -> dict:
    """{файл: (max_cc, назва блоку)}. Radon дублює методи всередині класів -- для max це неважливо."""
    with open(radon_json, encoding="utf-8-sig") as fh:  # utf-8-sig: терпимо до BOM з PowerShell
        data = json.load(fh)
    result = {}
    for file, blocks in data.items():
        if not isinstance(blocks, list):  # {"error": "..."} для файлів, які radon не зміг розібрати
            continue
        funcs, classes, stack = [], [], list(blocks)
        while stack:
            block = stack.pop()
            stack.extend(block.get("methods", []))
            target = funcs if block.get("type") in ("function", "method") else classes
            target.append((block["complexity"], block["name"]))
        pool = funcs or classes
        if pool:
            result[norm(file)] = max(pool)
    return result


def churn_from_git(days: int) -> Counter:
    """Те саме, що `git log --format=format: --name-only | grep -v '^$' | sort | uniq -c`."""
    out = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--format=format:", "--name-only"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    return Counter(norm(line) for line in out.splitlines() if line.strip())


def churn_from_file(path: str) -> Counter:
    """Формат `uniq -c`: '   7 path/to/file.py'."""
    counter = Counter()
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].isdigit():
                counter[norm(parts[1])] += int(parts[0])
    return counter


def classify(cc: int, churn: int, cc_threshold: int, churn_threshold: int) -> str:
    return CATEGORIES[(cc > cc_threshold, churn >= churn_threshold)]


def build_rows(cc_map, churn, cc_threshold, churn_threshold, exclude):
    rows = []
    for file, (cc, block) in cc_map.items():
        if any(part in file for part in exclude):
            continue
        commits = churn.get(file, 0)
        rows.append({
            "file": file, "cc": cc, "block": block, "commits": commits,
            "category": classify(cc, commits, cc_threshold, churn_threshold),
        })
    rows.sort(key=lambda r: (ORDER[r["category"]], -r["commits"], -r["cc"], r["file"]))
    return rows


def to_markdown(rows, cc_threshold, churn_threshold, days) -> str:
    lines = [
        f"### Hotspots (CC > {cc_threshold} = висока складність; "
        f"≥ {churn_threshold} комітів за {days} днів = висока мінливість)",
        "",
        "| Файл | Макс. CC (функція) | Коміти | Категорія ризику |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r['file']}` | {r['cc']} (`{r['block']}`) | {r['commits']} | {r['category']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cc", required=True, help="radon cc -j звіт")
    ap.add_argument("--churn", help="файл у форматі `uniq -c`; якщо не задано -- рахується з git log")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--cc-threshold", type=int, default=10)
    ap.add_argument("--churn-threshold", type=int, default=4)
    ap.add_argument("--exclude", nargs="*", default=["tests/", ".venv/", "node_modules/"])
    ap.add_argument("--out", default=".", help="тека для hotspots.md та hotspots.json")
    args = ap.parse_args()

    churn = churn_from_file(args.churn) if args.churn else churn_from_git(args.days)
    rows = build_rows(collect_cc(args.cc), churn, args.cc_threshold, args.churn_threshold, args.exclude)
    markdown = to_markdown(rows, args.cc_threshold, args.churn_threshold, args.days)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "hotspots.md"), "w", encoding="utf-8") as fh:
        fh.write(markdown)
    with open(os.path.join(args.out, "hotspots.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())