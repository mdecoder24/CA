import io
from datetime import date

from app.importers.kotak import find_period

APR = """Statement Period,01-04-2025 to 30-04-2025
Opening Balance,"10,000.00",CR
Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,05-04-2025,05-04-2025,UPI/SHOP/1/x,A1,"1,000.00",DR,"9,000.00",CR
2,20-04-2025,20-04-2025,UPI/SHOP/2/x,A2,"1,000.00",DR,"8,000.00",CR
"""
# May statement that continues correctly from 8,000
MAY = """Statement Period,01-05-2025 to 31-05-2025
Opening Balance,"8,000.00",CR
Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,03-05-2025,03-05-2025,UPI/SHOP/3/x,M1,"500.00",DR,"7,500.00",CR
"""
# July statement skipping June: opening does not continue from 7,500
JUL = """Statement Period,01-07-2025 to 15-07-2025
Opening Balance,"6,000.00",CR
Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,02-07-2025,02-07-2025,UPI/SHOP/4/x,J1,"100.00",DR,"5,900.00",CR
"""


def _up(client, name, text):
    r = client.post("/api/imports", files={"file": (name, io.BytesIO(text.encode()))}, data={"account_id": 1})
    assert r.status_code == 200, r.text
    return r.json()


def test_find_period_formats():
    assert find_period("Account Statement\n01 Apr 2026 - 10 Nov 2026\n") == (date(2026, 4, 1), date(2026, 11, 10))
    assert find_period("Statement Period,01-04-2025 to 30-04-2025") == (date(2025, 4, 1), date(2025, 4, 30))
    assert find_period("From : 01/05/25 To : 31/05/25") == (date(2025, 5, 1), date(2025, 5, 31))


def test_printed_period_and_continuity(client):
    a = _up(client, "apr.csv", APR)
    assert a["batch"]["period_from"] == "2025-04-01" and a["batch"]["period_to"] == "2025-04-30"
    assert a["continuity"]["checked"] is False
    m = _up(client, "may.csv", MAY)
    assert m["continuity"]["ok"] is True and m["continuity"]["checked"] is True
    j = _up(client, "jul.csv", JUL)
    assert j["continuity"]["ok"] is False and "may be missing" in j["continuity"]["message"]


def test_month_coverage(client):
    _up(client, "apr.csv", APR)
    _up(client, "jul.csv", JUL)
    cov = {c["month"]: c for c in client.get("/api/accounts/1/coverage", params={"fy": "2025-26"}).json()}
    assert cov["2025-04"]["status"] == "full" and cov["2025-04"]["txn_count"] == 2
    assert cov["2025-05"]["status"] == "missing"
    assert cov["2025-07"]["status"] == "partial" and cov["2025-07"]["covered_until"] == "2025-07-15"
    assert cov["2025-07"]["missing"] == [{"from": "2025-07-16", "to": "2025-07-31"}]
    assert client.get("/api/accounts/99/coverage", params={"fy": "2025-26"}).status_code == 404
