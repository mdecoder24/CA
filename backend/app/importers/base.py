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

    @property
    def period(self) -> tuple[Optional[date], Optional[date]]:
        if not self.rows:
            return None, None
        dates = [r.txn_date for r in self.rows]
        return min(dates), max(dates)


class BankParser(Protocol):
    bank: str

    def parse(self, path: Path, file_type: str, password: Optional[str] = None) -> ParsedStatement: ...
