import io

from app.tax.engine import compute, slab_tax, load_rules

from .conftest import KOTAK_CSV

FY = "2025-26"


def _new(res):
    return res["regimes"]["new"]


def test_slab_tax_new_regime():
    slabs = load_rules(FY)["regimes"]["new"]["slabs"]
    assert slab_tax(1_200_000, slabs) == 60_000
    assert slab_tax(1_300_000, slabs) == 75_000
    assert slab_tax(400_000, slabs) == 0


def test_rebate_wipes_tax_up_to_12_lakh():
    res = compute(FY, {}, {"salary": {"gross": 1_275_000}})
    assert _new(res)["total_income"] == 1_200_000
    assert _new(res)["liability"] == 0


def test_marginal_relief_just_above_limit():
    res = compute(FY, {}, {"salary": {"gross": 1_285_000}})
    # taxable 12.10L: slab tax 61,500 capped at excess 10,000 + 4% cess
    assert _new(res)["liability"] == 10_400


def test_no_relief_far_above_limit():
    res = compute(FY, {}, {"salary": {"gross": 1_375_000}})
    assert _new(res)["liability"] == 78_000


def test_old_regime_with_80c():
    res = compute(FY, {}, {"salary": {"gross": 1_050_000}, "deductions_old": {"80C": 200_000}})
    # 10.5L - 50k std - 1.5L (capped) = 8.5L -> 12,500 + 70,000 = 82,500 + 4% = 85,800
    assert res["regimes"]["old"]["liability"] == 85_800


def test_tds_grossed_up_once_and_credited():
    bank = {"profession": 900_000}  # net of 10% TDS
    res = compute(FY, bank, {"tds": [{"head": "profession", "deductor": "Client", "amount": 100_000}],
                             "profession": {"presumptive_44ada": True}})
    new = _new(res)
    gross = next(ln for ln in new["lines"] if ln["label"] == "Professional receipts (gross)")
    assert gross["amount"] == 1_000_000
    profit = next(ln for ln in new["lines"] if ln["label"] == "Profit from profession")
    assert profit["amount"] == 500_000
    assert new["total_income"] == 500_000
    assert new["liability"] == 0  # under rebate
    assert new["balance"] == -100_000  # full TDS refundable


def test_special_rate_gains_no_rebate():
    res = compute(FY, {}, {"salary": {"gross": 875_000}, "trading": {"stcg_111a": 100_000}})
    new = _new(res)
    # slab income 8L -> 30,000 tax, rebated; STCG 1L @20% = 20,000 not rebated; +4% cess
    assert new["liability"] == 20_800


def test_unconfirmed_credits_excluded_and_noted():
    res = compute(FY, {"unconfirmed_credits": 25_000}, {})
    assert any("EXCLUDED" in n for n in res["notes"])


def test_api_tax_and_reports(client):
    client.post("/api/imports", files={"file": ("a.csv", io.BytesIO(KOTAK_CSV.encode()))}, data={"account_id": 1})
    r = client.get(f"/api/tax/{FY}")
    assert r.status_code == 200
    est = r.json()["estimate"]
    assert est["disclaimer"].startswith("Estimate only")
    # salary is only 'suggested' -> excluded
    assert any("EXCLUDED" in n for n in est["notes"])
    r = client.put(f"/api/tax/{FY}/inputs", json={"salary": {"gross": 1_000_000}, "bogus": 1})
    assert r.status_code == 200 and "bogus" not in r.json()["inputs"]

    x = client.post(f"/api/reports/{FY}/excel")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    p = client.post(f"/api/reports/{FY}/pdf")
    assert p.status_code == 200 and p.content[:4] == b"%PDF"


def test_raw_transactions_are_immutable_via_api(client):
    from app.main import app

    client.post("/api/imports", files={"file": ("a.csv", io.BytesIO(KOTAK_CSV.encode()))}, data={"account_id": 1})
    tx = client.get("/api/transactions", params={"fy": FY}).json()[0]
    r = client.patch(f"/api/transactions/{tx['id']}/classification",
                     json={"category_id": None, "note": "hello", "raw_description": "HACKED", "credit": 1})
    assert r.status_code == 200
    after = client.get("/api/transactions", params={"fy": FY}).json()[0]
    assert after["raw_description"] == tx["raw_description"] and after["credit"] == tx["credit"]
    # No route can write raw transactions directly.
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path.startswith("/api/transactions/{tx_id}") and methods & {"PUT", "DELETE"}:
            raise AssertionError(f"Unexpected mutating route {path}")


def test_confirm_and_make_rule(client):
    client.post("/api/imports", files={"file": ("a.csv", io.BytesIO(KOTAK_CSV.encode()))}, data={"account_id": 1})
    txs = client.get("/api/transactions", params={"fy": FY}).json()
    rahul = next(t for t in txs if "RAHUL" in t["raw_description"])
    cats = client.get("/api/categories").json()
    prof = next(c for c in cats if c["treatment"] == "profession")
    r = client.patch(f"/api/transactions/{rahul['id']}/classification",
                     json={"category_id": prof["id"], "make_rule": True, "note": "Consulting invoice #12"})
    assert r.json()["rule_id"]
    est = client.get(f"/api/tax/{FY}").json()["estimate"]
    gross = next(ln for ln in est["regimes"]["new"]["lines"] if ln["label"] == "Professional receipts (gross)")
    assert gross["amount"] == 60_000


def test_write_without_header_rejected(client):
    r = client.post("/api/rules/rerun", headers={"X-FinTrack": ""})
    assert r.status_code == 403
