import io

HDFC_CSV = """HDFC BANK Ltd.
Account No : 50100123459999
Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/05/25,UPI-RAHUL SHARMA-rahul@okhdfc-HDFC0001-412345678901-dinner,0000412345678901,01/05/25,500.00,,9500.00
02/05/25,NEFT CR-ACME0001-ACME CORP-SALARY MAY,N12345,02/05/25,,50000.00,59500.00
05/05/25,IMPS-UPI-SELF-TRANSFER TO KOTAK,I999,05/05/25,20000.00,,39500.00
"""

KOTAK_CSV = """Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance,Dr / Cr
1,06-05-2025,06-05-2025,IMPS FROM HDFC SELF,K1,"20,000.00",CR,"30,000.00",CR
2,07-05-2025,07-05-2025,UPI/SHOP/1/x,K2,"1,000.00",DR,"29,000.00",CR
"""


def _add(client, bank, last4="", nickname=""):
    r = client.post("/api/accounts", json={"bank": bank, "last4": last4, "nickname": nickname})
    assert r.status_code == 200, r.text
    return r.json()


def _up(client, account_id, name, text, **form):
    return client.post("/api/imports", files={"file": (name, io.BytesIO(text.encode()))},
                       data={"account_id": account_id, **form})


def test_banks_and_accounts_crud(client):
    banks = {b["code"] for b in client.get("/api/banks").json()}
    assert {"kotak", "hdfc", "icici", "sbi", "axis"} <= banks
    hdfc = _add(client, "hdfc", "9999", "HDFC Salary")
    assert hdfc["masked_number"] == "XXXX9999" and hdfc["bank_name"] == "HDFC Bank"
    assert client.post("/api/accounts", json={"bank": "nope"}).status_code == 400
    assert client.post("/api/accounts", json={"bank": "sbi", "last4": "12"}).status_code == 400
    sbi = _add(client, "sbi")
    assert client.delete(f"/api/accounts/{sbi['id']}").status_code == 200
    assert len(client.get("/api/accounts").json()) == 2  # default Kotak + HDFC


def test_hdfc_import_and_account_filter(client):
    hdfc = _add(client, "hdfc", "9999")
    r = _up(client, hdfc["id"], "hdfc.csv", HDFC_CSV)
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 3 and r.json()["batch"]["status"] == "ok"
    txs = client.get("/api/transactions", params={"fy": "2025-26", "account_id": hdfc["id"]}).json()
    assert len(txs) == 3 and all(t["account_id"] == hdfc["id"] for t in txs)
    assert next(t for t in txs if "RAHUL" in t["raw_description"])["counterparty"] == "Rahul Sharma"
    assert client.get("/api/transactions", params={"fy": "2025-26", "account_id": 1}).json() == []


def test_account_mismatch_rejected(client):
    icici = _add(client, "icici", "1111")
    r = _up(client, icici["id"], "hdfc.csv", HDFC_CSV)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "account_mismatch"
    assert _up(client, icici["id"], "hdfc.csv", HDFC_CSV, force_account="true").status_code == 200


def test_own_transfer_matched_across_accounts(client):
    hdfc = _add(client, "hdfc", "9999")
    assert _up(client, hdfc["id"], "hdfc.csv", HDFC_CSV).status_code == 200
    assert _up(client, 1, "kotak.csv", KOTAK_CSV).status_code == 200
    txs = client.get("/api/transactions", params={"fy": "2025-26"}).json()
    out = next(t for t in txs if "TRANSFER TO KOTAK" in t["raw_description"])
    inn = next(t for t in txs if "FROM HDFC SELF" in t["raw_description"])
    assert out["category"] == inn["category"] == "Transfer – own account"
    assert out["source"] == inn["source"] == "match" and out["status"] == "suggested"
    # The ₹20,000 moved between own accounts is not spending.
    sp = client.get("/api/spend", params={"fy": "2025-26"}).json()
    assert sp["spend_total"] == 500_00 + 1_000_00
    dash = client.get("/api/dashboard", params={"fy": "2025-26"}).json()
    assert dash["closing_balance"] == 39_500_00 + 29_000_00
