import subprocess
import sys

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def main() -> int:
    staged_files = [f for f in sys.argv[1:] if f.endswith(".py")]
    if not staged_files:
        return 0

    result = subprocess.run(
        [sys.executable, "-m", "radon", "cc", "-n", "C", "-s", *staged_files],
        capture_output=True,
        text=True,
    )
    violations = result.stdout.strip()

    if violations:
        print(f"\n{RED}[QUALITY GATE BLOCKED] Перевищено ліміт складності (CC > 10)!{RESET}")
        print(f"{RED}Аномалії знайдено у Staged-файлах:{RESET}\n{violations}\n")
        print(f"{RED}Коміт скасовано. Застосуйте рефакторинг (Lookup Table) перед комітом.{RESET}")
        return 1

    print(f"{GREEN}[QUALITY GATE PASSED] Складність коду в нормі (CC <= 10).{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())