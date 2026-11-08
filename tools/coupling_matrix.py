#!/usr/bin/env python3
"""Coupling Matrix (клас x клас, на якого він посилається) з ck_metrics JSON -> PNG.

SonarQube Community не має вкладки Dependency / Coupling Matrix, тому матрицю
будуємо з `cbo_classes`, які вже порахував tools/ck_metrics.py.

Usage (з кореня репозиторію):
    python tools/ck_metrics.py my_fastapi_app --out docs/lab8/ck_before.json
    python tools/coupling_matrix.py docs/lab8/ck_before.json --focus privacy \
        --title "Baseline: God Object" --out docs/lab8/coupling_matrix_before.png

Потрібен matplotlib (pip install matplotlib). Рядок = клас, стовпчик = компонент,
на який посилається клас; сума по рядку = CBO.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def collect_rows(data: dict, focus: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    needles = [part for part in focus.split(",") if part]
    for rel, info in data["files"].items():
        if not any(needle in rel for needle in needles):
            continue
        for name, cls in info["classes"].items():
            rows[name] = cls["cbo_classes"]
    return rows


def build_matrix(rows: dict[str, list[str]]) -> tuple[list[str], list[str], list[list[int]]]:
    names = sorted(rows, key=lambda n: -len(rows[n]))
    columns = sorted({c for refs in rows.values() for c in refs})
    matrix = [[1 if col in rows[n] else 0 for col in columns] for n in names]
    return names, columns, matrix


def draw(names: list[str], columns: list[str], matrix: list[list[int]], title: str, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    width = max(8.0, 0.55 * len(columns) + 5)
    height = max(3.0, 0.5 * len(names) + 2.5)
    fig, ax = plt.subplots(figsize=(width, height))
    ax.imshow(matrix, cmap="Reds", vmin=0, vmax=1.4, aspect="auto")
    ax.set_xticks(range(len(columns)), labels=columns, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(names)), labels=[f"{n}  (CBO={sum(r)})" for n, r in zip(names, matrix)], fontsize=9)
    ax.set_xticks([x - 0.5 for x in range(1, len(columns))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(names))], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", length=0)
    ax.set_title(title, fontsize=11, fontweight="bold")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coupling Matrix from ck_metrics JSON")
    parser.add_argument("json_file")
    parser.add_argument("--focus", default="privacy", help="substring of file path to include")
    parser.add_argument("--title", default="Coupling Matrix")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rows = collect_rows(json.loads(Path(args.json_file).read_text(encoding="utf-8")), args.focus)
    if not rows:
        print(f"no classes found for focus '{args.focus}'")
        return 1
    names, columns, matrix = build_matrix(rows)
    draw(names, columns, matrix, args.title, Path(args.out))
    print(f"saved {args.out}: {len(names)} classes x {len(columns)} components")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())