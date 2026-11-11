import io

from .conftest import KOTAK_CSV


def _up(client, name, text):
    r = client.post("/api/imports", files={"file": (name, io.BytesIO(text.encode()))}, data={"account_id": 1})
    assert r.status_code == 200, r.text
    return r.json()


def test_spend_excludes_moved_money_and_scores(client):
    b = _up(client, "a.csv", KOTAK_CSV)
    r = client.get("/api/spend", params={"batch_id": b["batch"]["id"]})
    assert r.status_code == 200
    d = r.json()
    # Swiggy 450 is spend; Zerodha 20,000 is moved (trading), not spend.
    assert d["spend_total"] == 45000
    assert any(m["label"] == "Trading – funds to broker" and m["amount"] == 20_000_00 for m in d["moved"])
    assert d["categories"][0]["category"] == "Food & groceries"
    keys = {s["key"] for s in d["risk"]["signals"]}
    assert {"spend_vs_inflow", "runway", "low_balance", "trading"} <= keys
    assert 0 <= d["risk"]["score"] <= 100
    assert d["risk"]["level"] in {"low", "moderate", "high", "critical"}


def test_overspending_is_dangerous(client):
    csv = """Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,01-05-2025,01-05-2025,NEFT ACME SALARY,N1,"10,000.00",CR,"10,500.00",CR
2,02-05-2025,02-05-2025,UPI/SHOPKEEPER/1/x,U1,"8,000.00",DR,"2,500.00",CR
3,03-05-2025,03-05-2025,UPI/RESTAURANT/2/x,U2,"2,400.00",DR,100.00,CR
4,04-05-2025,04-05-2025,MIN BAL CHARGES,C1,50.00,DR,50.00,CR
"""
    _up(client, "o.csv", csv)
    d = client.get("/api/spend", params={"fy": "2025-26"}).json()
    sig = {s["key"]: s for s in d["risk"]["signals"]}
    assert sig["spend_vs_inflow"]["level"] == "danger"
    assert sig["runway"]["level"] == "danger"
    assert sig["penalties"]["level"] == "danger"
    assert d["risk"]["level"] in {"high", "critical"}


def test_spend_bad_params(client):
    assert client.get("/api/spend").status_code == 400
    assert client.get("/api/spend", params={"batch_id": 999}).status_code == 404
