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

# Additions applied once to existing databases (tracked by the "seed_version" setting),
# so rules the user deleted are not resurrected on every start.
SEED_V2_CATEGORIES = [
    ("Investment / FD redemption", "credit", "not_income"),
    ("Credit card bill", "debit", "expense"),
]
SEED_V2_RULES = [
    (r"sweep\s*(transfer|trf)\s*from|fd\s*premat|td\s*premat|redemption|redeem", "regex", "credit",
     "Investment / FD redemption", False, 12),
    (r"upi_cradj|\bcr\s*adj", "regex", "credit", "Refund / Reversal", False, 40),
    (r"sweep\s*(transfer|trf)\s*to", "regex", "debit", "Investments (MF / FD / other)", True, 12),
    (r"groww\s*invest|nach-mut|indian\s*clearing\s*corp|national\s*stock\s*exchange", "regex", "debit",
     "Investments (MF / FD / other)", False, 25),
    (r"bill\s*paid\s*to\s*credit\s*card|visaccpay|credit\s*card\s*(bill|payment)", "regex", "debit",
     "Credit card bill", True, 45),
    (r"^at[lw]/", "regex", "debit", "Cash withdrawal", True, 50),
    (r"program\s*fee|card\s*fee", "regex", "debit", "Bank charges", False, 72),
    (r"^pcd/", "regex", "debit", "Shopping", False, 85),
]
SEED_V3_RULES = [
    (r"^pg\s*os\w*cc\b|cheq\s*digital|\bcred\s*club|amex|card\s*bill", "regex", "debit", "Credit card bill", False, 44),
]
SEED_V4_CATEGORIES = [
    ("Loan given / money lent", "debit", "not_income"),
]
# Daily-interest and in-app "pocket" transfers used by app banks such as slice.
SEED_V5_RULES = [
    (r"interest\s*cr\b|interest\s*credit", "regex", "credit", "Interest – savings", True, 10),
    (r"round\s*ups?|monies\s*transfer", "regex", "credit", "Transfer – own account", False, 16),
    (r"round\s*ups?|monies\s*transfer", "regex", "debit", "Transfer – own account", False, 16),
]
SEED_VERSION = 5

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

    ver = s.get(Setting, "seed_version")
    current = (ver.value or {}).get("v", 1) if ver else 1
    if current < 2:
        existing = {(c.name, c.direction) for c in s.exec(select(Category))}
        for name, direction, treatment in SEED_V2_CATEGORIES:
            if (name, direction) not in existing:
                s.add(Category(profile_id=profile.id, name=name, direction=direction, treatment=treatment, sort=500))
        s.commit()
        cats = {(c.name, c.direction): c.id for c in s.exec(select(Category))}
        for pattern, mtype, direction, cat, auto, prio in SEED_V2_RULES:
            s.add(Rule(profile_id=profile.id, priority=prio, match_type=mtype, pattern=pattern,
                       direction=direction, category_id=cats[(cat, direction)], auto_confirm=auto, builtin=True))
    if current < 3:
        cats = {(c.name, c.direction): c.id for c in s.exec(select(Category))}
        for pattern, mtype, direction, cat, auto, prio in SEED_V3_RULES:
            s.add(Rule(profile_id=profile.id, priority=prio, match_type=mtype, pattern=pattern,
                       direction=direction, category_id=cats[(cat, direction)], auto_confirm=auto, builtin=True))
    if current < 4:
        existing = {(c.name, c.direction) for c in s.exec(select(Category))}
        for name, direction, treatment in SEED_V4_CATEGORIES:
            if (name, direction) not in existing:
                s.add(Category(profile_id=profile.id, name=name, direction=direction, treatment=treatment, sort=510))
    if current < 5:
        cats = {(c.name, c.direction): c.id for c in s.exec(select(Category))}
        for pattern, mtype, direction, cat, auto, prio in SEED_V5_RULES:
            s.add(Rule(profile_id=profile.id, priority=prio, match_type=mtype, pattern=pattern,
                       direction=direction, category_id=cats[(cat, direction)], auto_confirm=auto, builtin=True))
    if ver is None:
        s.add(Setting(key="seed_version", value={"v": SEED_VERSION}))
    else:
        ver.value = {"v": SEED_VERSION}
        s.add(ver)
    s.commit()
