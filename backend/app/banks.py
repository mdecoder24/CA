"""Supported banks and their statement parsers.

Indian bank statements share one shape (date, narration, ref, withdrawal,
deposit, balance), so every bank uses the header-detecting parser in
``importers/kotak.py``; it maps columns by name (HDFC "Withdrawal Amt.",
ICICI "Transaction Remarks", SBI "Txn Date", Axis "PARTICULARS"/"DR"/"CR"/"BAL"…).
A bank that needs special handling can get its own parser here later.
"""

from .importers.kotak import KotakParser

BANKS: dict[str, str] = {
    "kotak": "Kotak Mahindra Bank",
    "hdfc": "HDFC Bank",
    "icici": "ICICI Bank",
    "sbi": "State Bank of India",
    "axis": "Axis Bank",
    "idfc": "IDFC FIRST Bank",
    "yes": "Yes Bank",
    "indusind": "IndusInd Bank",
    "federal": "Federal Bank",
    "au": "AU Small Finance Bank",
    "idbi": "IDBI Bank",
    "rbl": "RBL Bank",
    "pnb": "Punjab National Bank",
    "bob": "Bank of Baroda",
    "canara": "Canara Bank",
    "union": "Union Bank of India",
    "boi": "Bank of India",
    "indian": "Indian Bank",
    "slice": "slice small finance bank",
    "jupiter": "Jupiter (Federal Bank)",
    "fi": "Fi (Federal Bank)",
    "airtel": "Airtel Payments Bank",
    "paytm": "Paytm Payments Bank",
    "other": "Other bank",
}

_GENERIC = KotakParser()


def bank_name(code: str) -> str:
    return BANKS.get(code, code)


def get_parser(code: str):
    return _GENERIC
