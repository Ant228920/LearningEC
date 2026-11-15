#!/usr/bin/env python3
"""CK (Chidamber-Kemerer) + MOOD metrics for a Python project. Stdlib only.

SonarQube does not provide CBO / LCOM / DIT / RFC / MHF / AHF / COF, so this
script computes them from the AST and writes JSON (same spirit as the Sonar
Web API output) plus markdown tables for the report.

Usage (from the repository root):
    python tools/ck_metrics.py my_fastapi_app \
        --files api/v1/endpoints/privacy.py repository/currency_repository.py schemas/privacy.py \
        --out ck_metrics.json

Definitions (Python adaptation, document them in the report):
  WMC   sum of McCabe cyclomatic complexity of the class methods
  CBO   distinct other classes referenced by the class (project + imported,
        builtins excluded); reported as cbo = cbo_project + cbo_external
  LCOM4 connected components of the method graph (methods are linked when they
        share a self.<attr> or call each other); 1 = cohesive; __init__ skipped
  LCOM* Henderson-Sellers normalised LCOM in [0, 1]; 0 = cohesive, 1 = no
        cohesion (the scale used in the lab: "LCOM -> 1" is bad, goal ~0.2)
  DIT   depth of inheritance, `object` is the root, so a class without a base
        has DIT = 1 and Base -> Mid -> Child gives 3. A base class that is not
        defined in the project (BaseModel, Enum, ...) counts as depth 1.
  RFC   methods of the class + distinct callee names used inside them
  PIM   public methods (no leading underscore, dunders excluded)
  OVR   methods overriding a method of a project-defined ancestor
  MHF   hidden (_name) methods / all methods, AHF the same for attributes
        (dunder names are ignored)
  COF   coupled ordered class pairs / (TC^2 - TC)
Module view (for function-based modules such as FastAPI endpoints):
  WMC_module, CBO_module, Ce (project modules imported), Ca (project modules
  importing this one), I = Ce / (Ca + Ce)
Known limits: class-likeness of external names is detected by capitalisation
(datetime is missed, typing names such as Optional/Dict are counted);
overrides of external base classes are not detected.

Every function here keeps cyclomatic complexity <= 10 (the repo's radon gate).
"""
from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRS = {"tests", "__pycache__", "scripts", ".venv", "venv", ".git", ".scannerwork", "node_modules"}
BUILTINS = set(dir(builtins))
FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
DECISION_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                  ast.IfExp, ast.Assert, ast.match_case)

CBO_LIMIT = 15
LCOM_STAR_LIMIT = 0.8
DIT_LIMIT = 3
PIM_LIMIT = 20


# --------------------------------------------------------------------------- helpers
def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def is_hidden(name: str) -> bool:
    return name.startswith("_") and not is_dunder(name)


def is_class_like(name: str) -> bool:
    return name[:1].isupper() and not name.isupper()


def ratio(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def node_weight(node: ast.AST) -> int:
    """Extra McCabe paths contributed by one AST node."""
    if isinstance(node, DECISION_NODES):
        return 1
    if isinstance(node, ast.comprehension):
        return 1 + len(node.ifs)
    if isinstance(node, ast.BoolOp):
        return len(node.values) - 1
    return 0


def cyclomatic(func: ast.AST) -> int:
    return 1 + sum(node_weight(n) for n in ast.walk(func) if n is not func)


def base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return base_name(node.value)
    return ast.unparse(node)


@dataclass
class ClassInfo:
    name: str
    file: str
    node: ast.ClassDef
    bases: list[str]
    methods: dict[str, ast.AST]


# --------------------------------------------------------------------------- imports
def collect_imports(tree: ast.AST) -> dict[str, str]:
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            names.update({(a.asname or a.name): module for a in node.names})
        elif isinstance(node, ast.Import):
            names.update({(a.asname or a.name).split(".")[0]: a.name for a in node.names})
    return names


def resolve_module(root: Path, module: str) -> str | None:
    """Return the project file (relative, posix) a dotted module name points to."""
    if not module or module.startswith("."):
        return None
    base = root.joinpath(*module.split("."))
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py").relative_to(root).as_posix()
    if (base / "__init__.py").is_file():
        return (base / "__init__.py").relative_to(root).as_posix()
    return None


def from_import_targets(root: Path, node: ast.ImportFrom) -> set[str]:
    targets = {resolve_module(root, f"{node.module}.{a.name}") for a in node.names}  # submodules
    targets.discard(None)
    if not targets:
        targets = {resolve_module(root, node.module)}
        targets.discard(None)
    return targets


def project_dependencies(root: Path, tree: ast.AST) -> set[str]:
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            deps |= from_import_targets(root, node)
        elif isinstance(node, ast.Import):
            deps |= {t for a in node.names if (t := resolve_module(root, a.name))}
    return deps


# --------------------------------------------------------------------------- class metrics
def referenced_classes(node: ast.AST, registry: dict[str, ClassInfo], imported: dict[str, str],
                       exclude: set[str]) -> set[str]:
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            ident = n.id
        elif isinstance(n, ast.Attribute):
            ident = n.attr
        else:
            continue
        if ident in exclude or ident in BUILTINS:
            continue
        if ident in registry or (ident in imported and is_class_like(ident)):
            found.add(ident)
    return found


def self_attr_uses(method: ast.AST, method_names: set[str]) -> tuple[set[str], set[str]]:
    attrs: set[str] = set()
    calls: set[str] = set()
    for n in ast.walk(method):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in ("self", "cls"):
            (calls if n.attr in method_names else attrs).add(n.attr)
    return attrs, calls


def find_root(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(parent: dict[str, str], a: str, b: str) -> None:
    parent[find_root(parent, a)] = find_root(parent, b)


def method_components(methods: dict[str, ast.AST]) -> tuple[int, dict[str, set[str]]]:
    """LCOM4 (connected components) and, per attribute, the methods that use it."""
    names = set(methods)
    parent = {m: m for m in methods}
    attr_owner: dict[str, str] = {}
    attr_users: dict[str, set[str]] = {}
    for name, fn in methods.items():
        attrs, calls = self_attr_uses(fn, names)
        for called in calls:
            union(parent, name, called)
        for attr in attrs:
            attr_users.setdefault(attr, set()).add(name)
            if attr in attr_owner:
                union(parent, name, attr_owner[attr])
            else:
                attr_owner[attr] = name
    return len({find_root(parent, m) for m in methods}), attr_users


def lcom_star(method_count: int, attr_users: dict[str, set[str]]) -> float:
    attr_count = len(attr_users)
    if method_count <= 1 or attr_count == 0:
        return 0.0
    mean_uses = sum(len(u) for u in attr_users.values()) / attr_count
    return round((mean_uses - method_count) / (1 - method_count), 3) or 0.0  # `or` turns -0.0 into 0.0


def lcom_metrics(cls: ClassInfo) -> tuple[int, float]:
    methods = {n: f for n, f in cls.methods.items() if n != "__init__"}
    if not methods:
        return 0, 0.0
    lcom4, attr_users = method_components(methods)
    return lcom4, lcom_star(len(methods), attr_users)


def ancestors(cls: ClassInfo, registry: dict[str, ClassInfo]) -> list[ClassInfo]:
    out: list[ClassInfo] = []
    stack, seen = list(cls.bases), {cls.name}
    while stack:
        name = stack.pop()
        if name in seen or name not in registry:
            continue
        seen.add(name)
        out.append(registry[name])
        stack.extend(registry[name].bases)
    return out


def dit(cls: ClassInfo, registry: dict[str, ClassInfo], trail: tuple[str, ...] = ()) -> int:
    if not cls.bases:
        return 1
    depths = []
    for base in cls.bases:
        if base in registry and base not in trail and base != cls.name:
            depths.append(1 + dit(registry[base], registry, trail + (cls.name,)))
        else:
            depths.append(2)  # external base: object -> base -> this class
    return max(depths)


def declared_attributes(cls: ClassInfo) -> set[str]:
    attrs: set[str] = set()
    for stmt in cls.node.body:
        if isinstance(stmt, ast.Assign):
            attrs |= {t.id for t in stmt.targets if isinstance(t, ast.Name)}
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            attrs.add(stmt.target.id)
    return attrs


def is_self_store(n: ast.AST) -> bool:
    return (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
            and isinstance(n.value, ast.Name) and n.value.id == "self")


def assigned_self_attributes(cls: ClassInfo) -> set[str]:
    return {n.attr for fn in cls.methods.values() for n in ast.walk(fn) if is_self_store(n)}


def class_attributes(cls: ClassInfo) -> set[str]:
    return {a for a in declared_attributes(cls) | assigned_self_attributes(cls) if not is_dunder(a)}


def called_names(cls: ClassInfo) -> set[str]:
    calls: set[str] = set()
    for fn in cls.methods.values():
        calls |= {base_name(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    return calls


def overridden_methods(cls: ClassInfo, registry: dict[str, ClassInfo]) -> list[str]:
    inherited = {m for anc in ancestors(cls, registry) for m in anc.methods}
    return sorted(m for m in cls.methods if m in inherited)


def class_flags(result: dict) -> list[str]:
    flags = []
    if result["cbo"] > CBO_LIMIT:
        flags.append(f"CBO>{CBO_LIMIT}")
    if result["lcom_star"] >= LCOM_STAR_LIMIT:
        flags.append("LCOM*->1")
    if result["dit"] >= DIT_LIMIT:
        flags.append(f"DIT>={DIT_LIMIT}")
    if result["pim"] > PIM_LIMIT:
        flags.append(f"PIM>{PIM_LIMIT}")
    if result["overridden"]:
        flags.append("overrides")
    return flags


def class_metrics(cls: ClassInfo, registry: dict[str, ClassInfo], imported: dict[str, str]) -> dict:
    refs = referenced_classes(cls.node, registry, imported, {cls.name})
    cbo_project = len(refs & registry.keys())
    cbo_external = len(refs - registry.keys())
    lcom4, lcom_star_value = lcom_metrics(cls)
    result = {
        "bases": cls.bases,
        "methods": len(cls.methods),
        "wmc": sum(cyclomatic(f) for f in cls.methods.values()),
        "cbo": cbo_project + cbo_external,
        "cbo_project": cbo_project,
        "cbo_external": cbo_external,
        "cbo_classes": sorted(refs),
        "lcom4": lcom4,
        "lcom_star": lcom_star_value,
        "dit": dit(cls, registry),
        "rfc": len(set(cls.methods) | called_names(cls)),
        "pim": sum(1 for m in cls.methods if not m.startswith("_")),
        "overridden": overridden_methods(cls, registry),
    }
    result["flags"] = class_flags(result)
    return result


# --------------------------------------------------------------------------- project scan
def parse_project(root: Path) -> dict[str, ast.Module]:
    parsed: dict[str, ast.Module] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in rel.parts[:-1]):
            continue
        try:
            parsed[rel.as_posix()] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"skip {rel}: {exc}", file=sys.stderr)
    return parsed


def build_registry(parsed: dict[str, ast.Module]) -> tuple[dict[str, ClassInfo], dict[str, list[ClassInfo]]]:
    registry: dict[str, ClassInfo] = {}
    by_file: dict[str, list[ClassInfo]] = {}
    for rel, tree in parsed.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                info = ClassInfo(
                    name=node.name, file=rel, node=node,
                    bases=[base_name(b) for b in node.bases],
                    methods={n.name: n for n in node.body if isinstance(n, FUNC_TYPES)},
                )
                registry[node.name] = info
                by_file.setdefault(rel, []).append(info)
    return registry, by_file


def module_view(tree: ast.Module, classes: list[ClassInfo], registry: dict[str, ClassInfo],
                deps: set[str], afferent: int) -> dict:
    functions = [n for n in tree.body if isinstance(n, FUNC_TYPES)]
    refs = referenced_classes(tree, registry, collect_imports(tree), {c.name for c in classes})
    ce = len(deps)
    return {
        "functions": len(functions),
        "classes": len(classes),
        "wmc_module": sum(cyclomatic(f) for f in functions)
        + sum(cyclomatic(m) for c in classes for m in c.methods.values()),
        "cbo_module": len(refs),
        "cbo_module_classes": sorted(refs),
        "ce": ce,
        "ca": afferent,
        "instability": round(ce / (afferent + ce), 2) if afferent + ce else 0.0,
        "imports_project": sorted(deps),
    }


def coupled_pairs(registry: dict[str, ClassInfo], parsed: dict[str, ast.Module]) -> int:
    """Ordered pairs (A, B) of project classes where A references B."""
    return sum(
        len(referenced_classes(c.node, registry, collect_imports(parsed[c.file]), {c.name}) & registry.keys())
        for c in registry.values()
    )


def hidden_ratio(names: list[str]) -> float:
    return ratio(sum(1 for n in names if is_hidden(n)), len(names))


def mood_metrics(registry: dict[str, ClassInfo], parsed: dict[str, ast.Module]) -> dict:
    classes = list(registry.values())
    methods = [m for c in classes for m in c.methods if not is_dunder(m)]
    attrs = [a for c in classes for a in class_attributes(c)]
    total = len(classes)
    couples = coupled_pairs(registry, parsed)
    mood = {
        "classes": total,
        "methods": len(methods),
        "attributes": len(attrs),
        "mhf": hidden_ratio(methods),
        "ahf": hidden_ratio(attrs),
        "cof": ratio(couples, total * total - total),
        "coupled_pairs": couples,
    }
    for key in ("mhf", "ahf", "cof"):
        mood[f"{key}_percent"] = round(mood[key] * 100, 1)
    return mood


def analyse(root: Path) -> dict:
    parsed = parse_project(root)
    registry, by_file = build_registry(parsed)
    deps = {rel: project_dependencies(root, tree) - {rel} for rel, tree in parsed.items()}
    afferent = {rel: sum(1 for d in deps.values() if rel in d) for rel in parsed}
    files: dict[str, dict] = {}
    for rel, tree in parsed.items():
        classes = by_file.get(rel, [])
        imported = collect_imports(tree)
        files[rel] = {
            "module": module_view(tree, classes, registry, deps[rel], afferent[rel]),
            "classes": {c.name: class_metrics(c, registry, imported) for c in classes},
        }
    return {"project": mood_metrics(registry, parsed), "files": files}


# --------------------------------------------------------------------------- output
def print_tables(result: dict, selected: list[str]) -> None:
    print("## Project (MOOD)\n")
    p = result["project"]
    print("| Classes | Methods | Attributes | MHF | AHF | COF |")
    print("|---|---|---|---|---|---|")
    print(f"| {p['classes']} | {p['methods']} | {p['attributes']} | {p['mhf_percent']}% | "
          f"{p['ahf_percent']}% | {p['cof_percent']}% |\n")
    print("## Module view\n")
    print("| File | functions | classes | WMC_module | CBO_module | Ce | Ca | I |")
    print("|---|---|---|---|---|---|---|---|")
    for rel in selected:
        m = result["files"][rel]["module"]
        print(f"| {rel} | {m['functions']} | {m['classes']} | {m['wmc_module']} | {m['cbo_module']} | "
              f"{m['ce']} | {m['ca']} | {m['instability']} |")
    print("\n## Class view\n")
    print("| File | Class | WMC | CBO | LCOM4 | LCOM* | DIT | RFC | PIM | Overridden | Flags |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for rel in selected:
        for name, c in result["files"][rel]["classes"].items():
            print(f"| {rel} | {name} | {c['wmc']} | {c['cbo']} | {c['lcom4']} | {c['lcom_star']} | "
                  f"{c['dit']} | {c['rfc']} | {c['pim']} | {len(c['overridden'])} | "
                  f"{', '.join(c['flags']) or '-'} |")


def main() -> int:
    parser = argparse.ArgumentParser(description="CK + MOOD metrics for a Python project")
    parser.add_argument("root", help="source root, e.g. my_fastapi_app")
    parser.add_argument("--files", nargs="*", help="files (relative to root) for the tables; default: all")
    parser.add_argument("--out", help="write full JSON here")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = analyse(root)
    selected = [f.replace("\\", "/") for f in args.files] if args.files else sorted(result["files"])
    missing = [f for f in selected if f not in result["files"]]
    if missing:
        print(f"not found under {root}: {missing}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print_tables(result, selected)
    return 0


if __name__ == "__main__":
    sys.exit(main())