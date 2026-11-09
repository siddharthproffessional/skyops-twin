import os
import time

os.environ["SKYOPS_AI_MODE"] = "offline"
os.environ["SKYOPS_DEMO_PACE"] = "0"
os.environ["SKYOPS_DB"] = "/tmp/skyops_test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def wait_done(c, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get("/api/state").json()
        if not s["running"] and s["incident"] and s["incident"]["status"] != "running":
            return s
        time.sleep(0.5)
    raise AssertionError("incident did not finish")


def test_sandstorm_end_to_end_with_websocket_and_approval():
    with TestClient(app) as c:
        c.post("/api/reset")
        with c.websocket_connect("/ws/operations") as ws:
            assert ws.receive_json()["type"] == "hello"
            r = c.post("/api/scenarios/sandstorm/inject")
            assert r.status_code == 200
            seen = set()
            while "recommendation" not in seen:
                seen.add(ws.receive_json()["type"])
        s = wait_done(c)
        assert {"message", "tool_call", "agent_status", "conflict", "plans", "review"} <= seen
        plans = s["incident"]["plans"]
        rec = next(p for p in plans if p.get("recommended"))
        base = next(p for p in plans if p["id"] == "baseline")
        assert rec["feasible"] and rec["metrics"]["passenger_delay_hours"] < base["metrics"]["passenger_delay_hours"]
        a = c.post(f"/api/plans/{rec['id']}/approve", json={"note": "test"})
        assert a.status_code == 200
        s2 = c.get("/api/state").json()
        assert s2["approved_plan"] == rec["id"] and s2["schedule_name"] == rec["name"]
        assert c.get("/api/audit").json()[0]["action"] == "plan_approved"


def test_reject_and_freetext_and_metar():
    with TestClient(app) as c:
        c.post("/api/reset")
        r = c.post("/api/events/freetext", json={"text": "Debris on runway 30L, closed for 45 minutes at 14:40"}).json()
        assert r["accepted"] and r["spec"]["type"] == "runway_closure"
        s = wait_done(c)
        rej = c.post("/api/plans/plan-a/reject", json={"note": "prefer manual"})
        assert rej.json()["decision"] == "rejected"
        bad = c.post("/api/events/freetext", json={"text": "the cafeteria ran out of coffee"}).json()
        assert bad["accepted"] is False
        c.post("/api/reset")
        m = c.post("/api/adapters/metar", json={"raw": "OSKY 091420Z 31038G45KT 0600 BLSA SCT010 34/12 Q1002"}).json()
        assert m["accepted"] and m["decoded"]["visibility_m"] == 600 and m["decoded"]["wind_kt"] == 38
        wait_done(c)


def test_invalid_requests():
    with TestClient(app) as c:
        c.post("/api/reset")
        assert c.post("/api/scenarios/nope/inject").status_code == 404
        assert c.post("/api/disruptions", json={"type": "alien_invasion"}).status_code == 422
        assert c.post("/api/plans/plan-a/approve", json={}).status_code == 404
