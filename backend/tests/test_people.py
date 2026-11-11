import io

CSV = """Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,01-05-2025,01-05-2025,Recd:IMPS/000000000001/Mr Exampl/KKBK/X1/IMPS,R1,"50,000.00",CR,"50,000.00",CR
2,02-05-2025,02-05-2025,SentIMPS000000000002Example/IDFB/IMPS,R2,"45,000.00",DR,"5,000.00",CR
3,03-05-2025,03-05-2025,UPI/SWIGGY/3/food,R3,"1,000.00",DR,"4,000.00",CR
4,04-05-2025,04-05-2025,UPI/Example Redd/4/Payment,R4,"2,000.00",CR,"6,000.00",CR
"""


def _setup(client):
    r = client.post("/api/imports", files={"file": ("p.csv", io.BytesIO(CSV.encode()))}, data={"account_id": 1})
    assert r.status_code == 200, r.text


def test_suggest_create_and_ledger(client):
    _setup(client)
    sug = client.get("/api/people-suggestions", params={"fy": "2025-26"}).json()
    assert sug and sug[0]["key"] == "exampl" and sug[0]["count"] == 3
    p = client.post("/api/people", json={"name": "Example Person", "pattern": sug[0]["pattern"]}).json()
    led = client.get(f"/api/people/{p['id']}/ledger", params={"fy": "2025-26"}).json()
    assert led["received"] == 52_000_00 and led["sent"] == 45_000_00 and led["net"] == 7_000_00
    assert [r["running_net"] for r in led["rows"]] == [50_000_00, 5_000_00, 7_000_00]
    assert client.get("/api/people-suggestions", params={"fy": "2025-26"}).json() == []
    lst = client.get("/api/people", params={"fy": "2025-26"}).json()
    assert lst[0]["count"] == 3
    txs = client.get("/api/transactions", params={"fy": "2025-26", "person_id": p["id"]}).json()
    assert len(txs) == 3 and all(t["person"] == "Example Person" for t in txs)


def test_tracked_person_excluded_from_spend(client):
    _setup(client)
    before = client.get("/api/spend", params={"fy": "2025-26"}).json()
    assert before["spend_total"] == 46_000_00
    client.post("/api/people", json={"name": "Example Person", "pattern": "exampl"})
    after = client.get("/api/spend", params={"fy": "2025-26"}).json()
    assert after["spend_total"] == 1_000_00
    assert after["people"][0]["net"] == 7_000_00


def test_bad_pattern_rejected(client):
    assert client.post("/api/people", json={"name": "X", "pattern": "("}).status_code == 400
    assert client.post("/api/people", json={"name": " ", "pattern": "x"}).status_code == 400
    assert client.get("/api/people", params={"fy": "nope"}).status_code == 400
