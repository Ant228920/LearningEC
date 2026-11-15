#!/usr/bin/env python3
"""
Software Economics simulator (Lab 9, Task 2).

Reads SonarQube Cloud report.json (sqale_index, ncloc), converts the technical
debt into money, models 6 months of discounted cash flow after refactoring
and writes FINANCIAL_LEDGER.md.

Usage:
    HOURLY_RATE=40 OVERLOAD_COEFF=1.3 DISCOUNT_RATE=0.01 \
        python financial_ledger.py [report.json] [FINANCIAL_LEDGER.md]
"""
import json
import os
import sys
from datetime import date

MONTHS = 6
LOST_HOURS_PER_100_LOC = 1.0  # industry rule: 1 engineering hour / month per 100 ncloc


def env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        sys.exit(f"ERROR: environment variable {name}={raw!r} is not a number")


def load_metrics(path):
    """Parse the SonarQube Cloud /api/measures/component response."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        component = data["component"]
        measures = {m["metric"]: m["value"] for m in component["measures"]}
        return {
            "key": component.get("key", "unknown"),
            "sqale_index": int(measures["sqale_index"]),
            "ncloc": int(measures["ncloc"]),
        }
    except FileNotFoundError:
        sys.exit(f"ERROR: file not found: {path}")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        sys.exit(f"ERROR: {path} is not a valid SonarQube measures report ({exc!r})")


def simulate(sqale_index, ncloc, hourly_rate, overload, discount):
    """Return principal, monthly cost of delay, cash-flow rows and payback month."""
    effective_rate = hourly_rate * overload

    # Principal = cost to fix all debt right now
    principal = (sqale_index / 60) * effective_rate

    # Cost of Delay = money lost every month by doing nothing (FAIL state)
    cost_of_delay = (ncloc / 100) * LOST_HOURS_PER_100_LOC * effective_rate

    rows = []
    npv = -principal          # investment made at t = 0
    payback = None
    for t in range(1, MONTHS + 1):
        factor = 1 / (1 + discount) ** t
        monthly_profit = cost_of_delay * factor     # discounted saving of month t
        npv += monthly_profit                       # cumulative NPV_t
        rows.append((t, factor, monthly_profit, npv))
        if npv > 0 and payback is None:
            payback = t
    return principal, cost_of_delay, rows, payback


def money(x):
    return f"${x:,.2f}"


def render_ledger(m, rate, overload, discount, principal, cod, rows, payback):
    status = "PASS" if rows[-1][3] > 0 else "FAIL"
    lines = [
        "# SOFTWARE ECONOMICS & FINANCIAL QUALITY LEDGER",
        "",
        f"_Generated: {date.today().isoformat()}_",
        "",
        "## 1. Вхідні параметри аудиту (System Baseline)",
        "",
        f"- Проєкт (Key): `{m['key']}`",
        f"- Масштаб системи (NCLOC): {m['ncloc']:,}",
        f"- Початковий технічний борг (SQALE Index): {m['sqale_index']:,} хв "
        f"({m['sqale_index'] / 60:.2f} люд.-год)",
        f"- HOURLY_RATE: ${rate:g}/год; OVERLOAD_COEFF: {overload:g}; "
        f"DISCOUNT_RATE: {discount:g} (на місяць)",
        "",
        "## 2. Капіталізація інвестиційних маркерів",
        "",
        f"- Тіло боргу (вартість рефакторингу), $: **{money(principal)}**",
        f"- Щомісячні збитки від бездіяльності (Cost of Delay), $: **{money(cod)}**",
        "",
        f"## 3. Динаміка окупності інвестицій у часі ({MONTHS} ітерацій)",
        "",
        "| Місяць | Коефіцієнт дисконтування | Щомісячний прибуток, $ | Кумулятивний NPV, $ |",
        "|---:|---:|---:|---:|",
    ]
    for t, factor, profit, npv in rows:
        lines.append(f"| {t} | {factor:.6f} | {profit:,.2f} | {npv:,.2f} |")

    lines += ["", "## 4. Фінальний інженерно-економічний вердикт", ""]
    if payback:
        lines.append(f"Точка виходу в нуль (Payback Period): окупність настає на "
                     f"**{payback}-му місяці** розробки.")
    else:
        lines.append(f"Інвестиції не окупаються протягом {MONTHS} місяців "
                     f"(NPV на {MONTHS}-му місяці = {money(rows[-1][3])}).")

    lines += ["", "## 5. СТАТУС ВОРІТ ЯКОСТІ (Quality Gate)", "", f"**{status}**"]
    if status == "FAIL":
        lines += ["", "> ⚠️ АРХІТЕКТУРНЕ ПОПЕРЕДЖЕННЯ: технічний борг занадто великий "
                      f"порівняно зі збитками від бездіяльності; рефакторинг не окупається "
                      f"за {MONTHS} місяців. Потрібне поетапне погашення боргу або "
                      "перегляд архітектури."]
    return "\n".join(lines) + "\n", status


def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else "report.json"
    ledger_path = sys.argv[2] if len(sys.argv) > 2 else "FINANCIAL_LEDGER.md"

    rate = env_float("HOURLY_RATE", 40.0)
    overload = env_float("OVERLOAD_COEFF", 1.3)
    discount = env_float("DISCOUNT_RATE", 0.01)
    if not 35 <= rate <= 50:
        print(f"WARNING: HOURLY_RATE={rate:g} is outside the lab range $35-$50/h", file=sys.stderr)

    m = load_metrics(report_path)
    principal, cod, rows, payback = simulate(
        m["sqale_index"], m["ncloc"], rate, overload, discount)

    text, status = render_ledger(m, rate, overload, discount,
                                 principal, cod, rows, payback)
    with open(ledger_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    print(f"Project: {m['key']}  ncloc={m['ncloc']:,}  sqale_index={m['sqale_index']:,} min")
    print(f"Principal (Remediation Cost): {money(principal)}")
    print(f"Cost of Delay / month:        {money(cod)}")
    print(f"{'Month':>5} {'Discount':>10} {'Profit, $':>14} {'NPV, $':>14}")
    for t, factor, profit, npv in rows:
        print(f"{t:>5} {factor:>10.6f} {profit:>14,.2f} {npv:>14,.2f}")
    print(f"Payback period: {payback if payback else 'not reached'}")
    print(f"Quality Gate: {status}")
    print(f"[OK] {ledger_path} generated successfully")
    sys.exit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()