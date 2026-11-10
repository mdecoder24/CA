"""Seed the default profile, account, categories, built-in rules and settings."""

from sqlmodel import Session, select

from .models import Account, Category, Profile, Rule, Setting

# (name, direction, treatment)
CREDIT_CATEGORIES = [
    ("Salary", "credit", "salary"),
    ("Freelance / Professional receipt", "credit", "profession"),
    ("Trading – payout from broker", "credit", "trading_capital"),
    ("Interest – savings", "credit", "interest_savings"),
    ("Interest – FD / other", "credit", "interest_other"),
    ("Dividend", "credit", "dividend"),
    ("Refund / Reversal", "credit", "not_income"),
    ("Gift – from relative", "credit", "gift_relative"),
    ("Gift – from non-relative", "credit", "gift_nonrelative"),
    ("Loan received", "credit", "not_income"),
    ("Loan repaid to me", "credit", "not_income"),
    ("Cash deposit (own cash)", "credit", "not_income"),
    ("Transfer – own account", "credit", "not_income"),
    ("Other income", "credit", "other_income"),
    ("Unexplained", "credit", "unexplained"),
]

DEBIT_CATEGORIES = [
    ("Trading – funds to broker", "debit", "trading_capital"),
    ("Business expense", "debit", "business_expense"),
    ("Tax payment", "debit", "tax_paid"),
    ("Rent", "debit", "expense"),
    ("Utilities & bills", "debit", "expense"),
    ("Food & groceries", "debit", "expense"),
    ("Shopping", "debit", "expense"),
    ("Travel", "debit", "expense"),
    ("EMI / Loan repayment", "debit", "expense"),
    ("Insurance", "debit", "expense"),
    ("Investments (MF / FD / other)", "debit", "not_income"),
    ("Transfer – own account", "debit", "not_income"),
    ("Transfer – family", "debit", "expense"),
    ("Cash withdrawal", "debit", "expense"),
    ("Bank charges", "debit", "expense"),
    ("Other expense", "debit", "expense"),
]

# (pattern, match_type, direction, category name, auto_confirm, priority)
# Patterns are case-insensitive. Derived from common Kotak narration styles;
# refine them as real statements arrive.
BUILTIN_RULES = [
    (r"\bint\.?\s*pd\b|interest\s+(paid|credit)|\bsb\s*int", "regex", "credit", "Interest – savings", True, 10),
    (r"\bfd\b.*\bint|\btd\b.*\bint|deposit\s+interest", "regex", "credit", "Interest – FD / other", False, 11),
    (r"\bsalary\b|\bsal\b|payroll", "regex", "credit", "Salary", False, 20),
    (r"\bdiv(idend)?\b|\bach\b.*div", "regex", "credit", "Dividend", False, 25),
    (r"zerodha|upstox|groww|angel\s*one|angelbroking|icici\s*sec|kotak\s*sec|dhan\b|5paisa|motilal|sharekhan|indmoney|paytm\s*money",
     "regex", "credit", "Trading – payout from broker", False, 30),
    (r"zerodha|upstox|groww|angel\s*one|angelbroking|icici\s*sec|kotak\s*sec|dhan\b|5paisa|motilal|sharekhan|indmoney|paytm\s*money",
     "regex", "debit", "Trading – funds to broker", True, 30),
    (r"\brev(ersal)?\b|refund|\brfnd\b|cashback", "regex", "credit", "Refund / Reversal", False, 40),
    (r"cash\s*dep|\bcdm\b|by\s+cash", "regex", "credit", "Cash deposit (own cash)", False, 50),
    (r"\batm\b|\bnwd\b|cash\s*wdl|cash\s*withdrawal", "regex", "debit", "Cash withdrawal", True, 50),
    (r"advance\s*tax|self\s*assessment|\btin\b|income\s*tax|\bcbdt\b|e-?pay\s*tax", "regex", "debit", "Tax payment", False, 15),
    (r"\bemi\b|loan\s*rec|\bnach\b.*loan", "regex", "debit", "EMI / Loan repayment", False, 60),
    (r"\bchrg|charges|\bgst\s*on|sms\s*alert|annual\s*fee|debit\s*card\s*fee", "regex", "debit", "Bank charges", True, 70),
    (r"insurance|\blic\b|policy", "regex", "debit", "Insurance", False, 70),
    (r"swiggy|zomato|blinkit|zepto|bigbasket|instamart|dmart", "regex", "debit", "Food & groceries", True, 80),
    (r"amazon|flipkart|myntra|ajio|meesho|nykaa", "regex", "debit", "Shopping", False, 80),
    (r"irctc|uber|ola\b|rapido|makemytrip|indigo|air\s*india|goibibo|redbus", "regex", "debit", "Travel", True, 80),
    (r"electricity|bescom|msedcl|tata\s*power|airtel|jio|vodafone|\bvi\b|broadband|gas\s*bill|recharge", "regex",
     "debit", "Utilities & bills", True, 80),
    (r"mutual\s*fund|\bmf\b|\bsip\b|bse\s*star|cams|kfin|nps", "regex", "debit", "Investments (MF / FD / other)", False, 80),
]

DEFAULT_SETTINGS = {
    "anomaly": {"large_credit_paise": 50_000_00, "round_repeat_min": 3, "round_unit_paise": 1_000_00},
    "ollama": {"enabled": False, "url": "http://127.0.0.1:11434", "model": "qwen2.5:7b"},
}


def seed(s: Session) -> None:
    profile = s.exec(select(Profile)).first()
    if profile is None:
        profile = Profile(name="Personal")
        s.add(profile)
        s.commit()
        s.refresh(profile)

    if s.exec(select(Account)).first() is None:
        s.add(Account(profile_id=profile.id, bank="kotak", nickname="Kotak Savings"))

    if s.exec(select(Category)).first() is None:
        for i, (name, direction, treatment) in enumerate(CREDIT_CATEGORIES + DEBIT_CATEGORIES):
            s.add(Category(profile_id=profile.id, name=name, direction=direction, treatment=treatment, sort=i))
        s.commit()

    if s.exec(select(Rule)).first() is None:
        cats = {(c.name, c.direction): c.id for c in s.exec(select(Category))}
        for pattern, mtype, direction, cat, auto, prio in BUILTIN_RULES:
            s.add(Rule(profile_id=profile.id, priority=prio, match_type=mtype, pattern=pattern,
                       direction=direction, category_id=cats[(cat, direction)], auto_confirm=auto, builtin=True))

    for key, value in DEFAULT_SETTINGS.items():
        if s.get(Setting, key) is None:
            s.add(Setting(key=key, value=value))

    s.commit()
