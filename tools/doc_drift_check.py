#!/usr/bin/env python3
"""Doc Drift Check: перевіряє, що архітектурна документація відповідає коду. Stdlib only.

Запуск з КОРЕНЯ репозиторію:
    python tools/doc_drift_check.py

Що перевіряється (правило супроводу «зміна коду = зміна документації»):
  1. Кожен HTTP-маршрут із коду (декоратори FastAPI) згаданий у docs/sdd.md.
  2. Кожен сервіс my_fastapi_app/docker-compose.yml має розділ `## <сервіс>` у docs/isd.md.
  3. Залежності запуску (depends_on) у compose збігаються з таблицею
     «Залежності запуску» в docs/isd.md.

Код завершення: 0 — розбіжностей немає, 1 — виявлено дрейф документації.
"""
import re
import sys
from pathlib import Path

APP = Path("my_fastapi_app")
COMPOSE = APP / "docker-compose.yml"
SDD = Path("docs/sdd.md")
ISD = Path("docs/isd.md")

ROUTE_RE = re.compile(r"@\w+\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']")
ROW_RE = re.compile(r"^\|\s*([A-Za-z0-9_-]+)\s*\|\s*(.*?)\s*\|\s*$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_routes() -> list[tuple[str, str, str]]:
    sources = [APP / "main.py", *sorted((APP / "api" / "v1" / "endpoints").glob("*.py"))]
    found = []
    for src in sources:
        for method, path in ROUTE_RE.findall(read(src)):
            found.append((method.upper(), path, src.as_posix()))
    return found


def compose_service_blocks(text: str) -> dict[str, str]:
    section = re.search(r"^services:\s*\n(.*?)(?=^\S|\Z)", text, re.S | re.M)
    parts = re.split(r"^  ([A-Za-z0-9_-]+):\s*$", section.group(1) if section else "", flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def block_dependencies(block: str) -> set[str]:
    depends = re.search(r"^    depends_on:\s*\n((?:      .*\n?)*)", block, re.M)
    return set(re.findall(r"^      ([A-Za-z0-9_-]+):", depends.group(1), re.M)) if depends else set()


def compose_dependencies() -> dict[str, set[str]]:
    blocks = compose_service_blocks(read(COMPOSE))
    return {name: block_dependencies(block) for name, block in blocks.items()}


def isd_dependency_table(isd_text: str, services: set[str]) -> dict[str, set[str]]:
    table = {}
    for line in isd_text.splitlines():
        row = ROW_RE.match(line)
        if row and row.group(1) in services:
            names = set(re.findall(r"[A-Za-z0-9_-]+", row.group(2)))
            table[row.group(1)] = names & services
    return table


def check_routes() -> list[str]:
    sdd_text = read(SDD)
    return [
        f"маршрут {method} {path} є в коді ({src}), але відсутній у {SDD.as_posix()}"
        for method, path, src in code_routes()
        if path not in sdd_text
    ]


def check_services(deps: dict[str, set[str]]) -> list[str]:
    isd_text = read(ISD)
    return [
        f"сервіс {name} є в {COMPOSE.as_posix()}, але немає розділу '## {name}' в {ISD.as_posix()}"
        for name in deps
        if f"## {name}" not in isd_text
    ]


def check_dependencies(deps: dict[str, set[str]]) -> list[str]:
    table = isd_dependency_table(read(ISD), set(deps))
    problems = []
    for name, actual in deps.items():
        documented = table.get(name)
        if documented is None:
            problems.append(f"сервіс {name}: немає рядка в таблиці 'Залежності запуску' ({ISD.as_posix()})")
        elif documented != actual:
            problems.append(
                f"сервіс {name}: у compose depends_on={sorted(actual)}, "
                f"в ISD задокументовано {sorted(documented)}"
            )
    return problems


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    deps = compose_dependencies()
    problems = check_routes() + check_services(deps) + check_dependencies(deps)
    for problem in problems:
        print(f"[DOC-DRIFT] ✗ {problem}")
    if problems:
        print(f"RESULT: FAIL — виявлено розбіжностей між кодом і документацією: {len(problems)}")
        return 1
    print("RESULT: PASS — документація відповідає коду (маршрути, сервіси, залежності запуску)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
