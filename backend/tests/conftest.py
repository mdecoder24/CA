"""Test fixtures. All statements here are synthetic — never commit real bank data."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTRACK_DATA_DIR", str(tmp_path / "data"))
    from app import db

    db.reset_engine()
    from app.main import app

    with TestClient(app, headers={"X-FinTrack": "1"}) as c:
        yield c
    db.reset_engine()


# Opening balance 10,000.00. Kotak net-banking style: Amount + Dr/Cr, Balance + Dr/Cr.
KOTAK_CSV = """Kotak Mahindra Bank
Account No.,XXXXXXXX1234
Statement Period,01-04-2025 to 30-04-2025
Opening Balance,"10,000.00",CR

Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,01-04-2025,01-04-2025,NEFT ACME TECHNOLOGIES PVT LTD SALARY APR,NEFT001,"85,000.00",CR,"95,000.00",CR
2,03-04-2025,03-04-2025,UPI/SWIGGY/509312345678/food,UPI0001,450.00,DR,"94,550.00",CR
3,05-04-2025,05-04-2025,IMPS/ZERODHA BROKING LTD/FUNDS,IMPS01,"20,000.00",DR,"74,550.00",CR
4,10-04-2025,10-04-2025,UPI/RAHUL SHARMA/509399999999/consulting,UPI0002,"60,000.00",CR,"1,34,550.00",CR
5,12-04-2025,12-04-2025,CASH DEPOSIT CDM MUMBAI,CDM01,"25,000.00",CR,"1,59,550.00",CR
6,30-04-2025,30-04-2025,Int.Pd:01-04-2025 to 30-04-2025,,312.00,CR,"1,59,862.00",CR
"""
