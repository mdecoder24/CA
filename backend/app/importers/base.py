"""Bank statement parser interface.

New banks (or an Account Aggregator feed) plug in by implementing BankParser.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional, Protocol


class StatementError(Exception):
    """The file could not be read as a bank statement."""


class PasswordRequired(StatementError):
    """The PDF is encrypted and no (or a wrong) password was supplied."""


@dataclass
class ParsedRow:
    txn_date: date
    description: str
    debit: int  # paise
    credit: int  # paise
    balance: Optional[int]  # paise
    value_date: Optional[date] = None
    ref_no: str = ""


@dataclass
class ParsedStatement:
    rows: list[ParsedRow]
    opening_balance: Optional[int] = None
    closing_balance: Optional[int] = None
    masked_account: str = ""
    notes: list[str] = field(default_factory=list)
    # Period printed on the statement ("01 Apr 2026 - 10 Nov 2026"), if found.
    stmt_from: Optional[date] = None
    stmt_to: Optional[date] = None

    @property
    def period(self) -> tuple[Optional[date], Optional[date]]:
        if not self.rows:
            return self.stmt_from, self.stmt_to
        dates = [r.txn_date for r in self.rows]
        lo, hi = min(dates), max(dates)
        # Use the printed period only when it actually contains every transaction.
        if self.stmt_from and self.stmt_to and self.stmt_from <= lo and hi <= self.stmt_to:
            return self.stmt_from, self.stmt_to
        return lo, hi


class BankParser(Protocol):
    bank: str

    def parse(self, path: Path, file_type: str, password: Optional[str] = None) -> ParsedStatement: ...
