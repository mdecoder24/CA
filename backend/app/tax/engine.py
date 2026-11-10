"""Tax estimate engine.

Pure functions: given bank aggregates (from confirmed classifications) and
manual inputs, compute old- and new-regime liability using the FY rule file.
All amounts in this module are whole rupees (float during computation, rounded
at the end). Every output line carries a `source` for traceability.

THIS IS AN ESTIMATE FOR DISCUSSION WITH A CA, NOT A FILING COMPUTATION.
Not modelled: surcharge marginal relief, loss carry-forward, senior-citizen
slabs, AMT, house-property income other than home-loan interest, clubbing.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).parent / "rules"

# Category treatments understood by the engine.
TREATMENTS = {
    "salary", "profession", "interest_savings", "interest_other", "dividend", "gift_relative",
    "gift_nonrelative", "other_income", "trading_capital", "not_income", "unexplained",
    "business_expense", "tax_paid", "expense",
}

DEFAULT_INPUTS: dict[str, Any] = {
    "salary": {"gross": None, "exempt_allowances": 0, "hra_exempt": 0, "professional_tax": 0,
               "employer_nps_80ccd2": 0},
    "tds": [],  # [{"head": salary|profession|interest|dividend|other, "deductor": str, "amount": n}]
    "taxes_paid": [],  # [{"kind": advance|self_assessment, "date": "YYYY-MM-DD", "amount": n}]
    "deductions_old": {"80C": 0, "80D": 0, "80CCD1B": 0, "80G": 0, "home_loan_interest": 0, "other": 0},
    "trading": {"intraday_pnl": 0, "fno_pnl": 0, "fno_turnover": 0, "stcg_111a": 0, "ltcg_112a": 0,
                "other_cg_slab": 0},
    "profession": {"presumptive_44ada": False, "extra_expenses": 0},
}


def available_fys() -> list[str]:
    return sorted(p.stem for p in RULES_DIR.glob("*.yaml"))


@lru_cache
def load_rules(fy: str) -> dict:
    path = RULES_DIR / f"{fy}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No tax rule file for FY {fy}. Available: {', '.join(available_fys())}")
    return yaml.safe_load(path.read_text())


def merge_inputs(stored: dict | None) -> dict:
    out = copy.deepcopy(DEFAULT_INPUTS)
    for k, v in (stored or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def _n(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def slab_tax(income: float, slabs: list) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        top = income if upper is None else min(income, upper)
        if top > lower:
            tax += (top - lower) * rate / 100
        if upper is None or income <= upper:
            break
        lower = upper
    return tax


def _surcharge_rate(income: float, bands: list) -> float:
    rate = 0.0
    for above, r in bands:
        if income > above:
            rate = r
    return rate


def compute(fy: str, bank: dict, inputs: dict) -> dict:
    """bank: rupee totals keyed by treatment (confirmed only) + 'unconfirmed_credits'."""
    rules = load_rules(fy)
    inp = merge_inputs(inputs)
    notes: list[str] = []

    tds_by_head: dict[str, float] = {}
    for t in inp["tds"]:
        tds_by_head[t.get("head", "other")] = tds_by_head.get(t.get("head", "other"), 0) + _n(t.get("amount"))
    tds_total = sum(tds_by_head.values())
    paid_total = sum(_n(p.get("amount")) for p in inp["taxes_paid"])

    # ---- Salary (gross) --------------------------------------------------
    sal = inp["salary"]
    salary_bank = _n(bank.get("salary"))
    if sal.get("gross") not in (None, "", 0):
        salary_gross = _n(sal["gross"])
        salary_src = "Form 16 / payslip (entered)"
    else:
        salary_gross = salary_bank + tds_by_head.get("salary", 0) + _n(sal.get("professional_tax"))
        salary_src = "Estimated from bank: net salary credits + salary TDS + professional tax"
        if salary_bank:
            notes.append("Gross salary is estimated from bank credits. Enter Form 16 figures for accuracy.")

    # ---- Profession (44ADA) -------------------------------------------------
    prof_net = _n(bank.get("profession"))
    prof_gross = prof_net + tds_by_head.get("profession", 0)
    p = inp["profession"]
    pres = rules["presumptive_44ada"]
    if p.get("presumptive_44ada"):
        prof_profit = prof_gross * pres["deemed_profit_pct"] / 100
        prof_src = f"Presumptive: {pres['deemed_profit_pct']}% of gross receipts"
        if prof_gross > pres["receipts_limit"]:
            notes.append(f"Professional receipts exceed ₹{pres['receipts_limit']:,.0f}; presumptive scheme may not apply.")
    else:
        expenses = _n(bank.get("business_expense")) + _n(p.get("extra_expenses"))
        prof_profit = prof_gross - expenses
        prof_src = f"Gross receipts − expenses (₹{expenses:,.0f} tagged business expense + manual)"

    # ---- Trading ---------------------------------------------------------
    tr = inp["trading"]
    intraday = _n(tr.get("intraday_pnl"))
    fno = _n(tr.get("fno_pnl"))
    if intraday < 0:
        notes.append(f"Intraday (speculative) loss of ₹{-intraday:,.0f} cannot offset other income; ignored here "
                     "(can be carried forward — ask your CA).")
        intraday = 0
    business_income = prof_profit + fno + intraday

    # ---- Other sources -----------------------------------------------------
    int_sav = _n(bank.get("interest_savings"))
    int_other = _n(bank.get("interest_other")) + tds_by_head.get("interest", 0)
    dividend = _n(bank.get("dividend")) + tds_by_head.get("dividend", 0)
    other_inc = _n(bank.get("other_income")) + tds_by_head.get("other", 0)
    gifts_nr = _n(bank.get("gift_nonrelative"))
    gifts_taxable = gifts_nr if gifts_nr > rules["gift_nonrelative_threshold"] else 0
    if gifts_nr and not gifts_taxable:
        notes.append(f"Gifts from non-relatives total ₹{gifts_nr:,.0f}, within the ₹"
                     f"{rules['gift_nonrelative_threshold']:,.0f} exemption.")
    other_sources = int_sav + int_other + dividend + other_inc + gifts_taxable

    # ---- Capital gains ---------------------------------------------------
    stcg = _n(tr.get("stcg_111a"))
    ltcg = _n(tr.get("ltcg_112a"))
    other_cg = _n(tr.get("other_cg_slab"))
    if stcg < 0:
        ltcg += stcg  # STCL can offset LTCG
        stcg = 0
    if ltcg < 0:
        notes.append("Net capital loss is not set off against other income here (carry-forward — ask your CA).")
        ltcg = 0
    if other_cg < 0:
        other_cg = 0

    # Business loss (non-speculative) offsets other heads except salary.
    if business_income < 0:
        loss = -business_income
        used = min(other_sources, loss)
        other_sources -= used
        loss -= used
        used = min(other_cg, loss)
        other_cg -= used
        loss -= used
        if loss > 0:
            notes.append(f"Unabsorbed business loss of ₹{loss:,.0f} (carry-forward — ask your CA).")
        business_income = 0

    regimes = {}
    for key, reg in rules["regimes"].items():
        lines: list[dict] = []

        def line(label, amount, source="", kind="row"):
            lines.append({"label": label, "amount": round(amount), "source": source, "kind": kind})

        if key == "new":
            salary_taxable = max(0.0, salary_gross - reg["standard_deduction"] - _n(sal.get("employer_nps_80ccd2")))
        else:
            salary_taxable = max(0.0, salary_gross - _n(sal.get("exempt_allowances")) - _n(sal.get("hra_exempt"))
                                 - _n(sal.get("professional_tax")) - reg["standard_deduction"]
                                 - _n(sal.get("employer_nps_80ccd2")))
        line("Salary (gross)", salary_gross, salary_src)
        line("Salary (taxable after standard deduction etc.)", salary_taxable, f"Std. deduction ₹{reg['standard_deduction']:,}")

        house_property = 0.0
        if reg.get("allow_deductions"):
            hli = min(_n(inp["deductions_old"].get("home_loan_interest")), reg["caps"]["home_loan_interest"])
            house_property = -hli
            if hli:
                line("House property (home-loan interest)", house_property, "Self-occupied, capped")

        line("Professional receipts (gross)", prof_gross, "Bank credits + profession TDS")
        line("Profit from profession", prof_profit, prof_src)
        if fno or intraday:
            line("F&O / intraday result", fno + intraday, "Manual entry (trading)")
        line("Business / profession income", business_income)
        line("Other sources", other_sources, "Interest, dividend, other income, taxable gifts (+ TDS gross-up)")
        if other_cg:
            line("Capital gains at slab rate", other_cg, "Manual entry")

        gti_normal = max(0.0, salary_taxable + house_property) + business_income + other_sources + other_cg
        special_total = stcg + max(0.0, ltcg)

        deductions = 0.0
        if reg.get("allow_deductions"):
            caps = reg["caps"]
            d = inp["deductions_old"]
            parts = {
                "80C": min(_n(d.get("80C")), caps["80C"]),
                "80CCD(1B)": min(_n(d.get("80CCD1B")), caps["80CCD1B"]),
                "80D": min(_n(d.get("80D")), caps["80D"]),
                "80TTA": min(int_sav, caps["80TTA"]),
                "80G": _n(d.get("80G")),
                "Other": _n(d.get("other")),
            }
            deductions = min(sum(parts.values()), gti_normal)  # not against special-rate gains
            line("Chapter VI-A deductions", -deductions, ", ".join(f"{k} ₹{v:,.0f}" for k, v in parts.items() if v))

        normal_income = max(0.0, gti_normal - deductions)
        total_income = normal_income + special_total
        line("Total taxable income", total_income, kind="total")

        tax_normal = slab_tax(normal_income, reg["slabs"])
        basic_exempt = reg["slabs"][0][0]
        shortfall = max(0.0, basic_exempt - normal_income)
        stcg_t = max(0.0, stcg - shortfall)
        shortfall = max(0.0, shortfall - stcg)
        ltcg_after_ex = max(0.0, ltcg - rules["special_rates"]["ltcg_112a_exemption"])
        ltcg_t = max(0.0, ltcg_after_ex - shortfall)
        tax_special = stcg_t * rules["special_rates"]["stcg_111a_pct"] / 100 + \
            ltcg_t * rules["special_rates"]["ltcg_112a_pct"] / 100

        line("Tax on slab income", tax_normal, f"Slabs, {reg['name']}")
        if special_total:
            line("Tax on special-rate gains (111A / 112A)", tax_special,
                 f"STCG {rules['special_rates']['stcg_111a_pct']}%, LTCG {rules['special_rates']['ltcg_112a_pct']}% "
                 f"above ₹{rules['special_rates']['ltcg_112a_exemption']:,}")

        rebate = 0.0
        if total_income <= reg["rebate_income_limit"]:
            rebate = min(reg["rebate_max"], tax_normal)
        elif reg.get("marginal_relief"):
            excess = total_income - reg["rebate_income_limit"]
            # Relief: tax may not exceed the income above the rebate limit (slab income only).
            if special_total == 0 and tax_normal > excess:
                rebate = tax_normal - excess
        if rebate:
            line("Rebate (87A / marginal relief)", -rebate, f"Income up to ₹{reg['rebate_income_limit']:,}")

        s_rate = _surcharge_rate(total_income, reg["surcharge"])
        surcharge = (tax_normal - rebate) * s_rate / 100 + \
            tax_special * min(s_rate, rules["special_rates"]["surcharge_cap_pct"]) / 100
        if surcharge:
            line(f"Surcharge ({s_rate:g}%)", surcharge, "Marginal relief on surcharge not modelled")
        cess = (tax_normal - rebate + tax_special + surcharge) * rules["cess_pct"] / 100
        line(f"Health & education cess ({rules['cess_pct']}%)", cess)
        liability = max(0.0, tax_normal - rebate + tax_special + surcharge + cess)
        line("Total tax liability", liability, kind="total")
        line("Less: TDS", -tds_total, f"{len(inp['tds'])} entries")
        line("Less: advance / self-assessment tax", -paid_total, f"{len(inp['taxes_paid'])} entries")
        balance = liability - tds_total - paid_total
        line("Balance payable" if balance >= 0 else "Refund due", abs(balance), kind="grand")

        regimes[key] = {"name": reg["name"], "lines": lines, "total_income": round(total_income),
                        "liability": round(liability), "balance": round(balance)}

    better = min(regimes, key=lambda k: regimes[k]["liability"])
    unconfirmed = _n(bank.get("unconfirmed_credits"))
    if unconfirmed:
        notes.insert(0, f"₹{unconfirmed:,.0f} of credits are not yet confirmed and are EXCLUDED from this estimate.")
    if not rules.get("verified", False):
        notes.insert(0, f"Tax rules for FY {fy} are not yet verified against official sources.")

    return {
        "fy": fy, "label": rules["label"], "act": rules["act"], "verified": bool(rules.get("verified")),
        "regimes": regimes, "recommended": better, "notes": notes,
        "salary_bank_net": round(salary_bank), "tds_total": round(tds_total), "taxes_paid_total": round(paid_total),
        "disclaimer": "Estimate only. Confirm with your CA before filing.",
    }
