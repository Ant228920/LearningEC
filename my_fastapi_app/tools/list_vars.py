import ast, sys
from collections import defaultdict

path, func_name = sys.argv[1], sys.argv[2]
tree = ast.parse(open(path, encoding="utf-8").read())
func = next(n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name)

stores, loads = defaultdict(list), defaultdict(list)
for arg in func.args.args + func.args.kwonlyargs:
    stores[arg.arg].append(f"{arg.lineno}(arg)")
for node in ast.walk(func):
    if isinstance(node, ast.Name):
        (stores if isinstance(node.ctx, ast.Store) else loads)[node.id].append(node.lineno)

names = sorted(set(stores) | {n for n in loads if n in stores})
print(f"{'змінна':<18}{'записи (рядки)':<22}читання (рядки)")
for n in names:
    print(f"{n:<18}{str(stores[n]):<22}{sorted(set(loads[n]))}")