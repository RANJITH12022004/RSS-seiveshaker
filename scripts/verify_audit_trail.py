#!/usr/bin/env python3
"""End-to-end audit trail verification against the running kiosk API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

BASE = os.environ.get("KIOSK_API_BASE", "http://127.0.0.1:5000")
TEST_USER = os.environ.get("AUDIT_TEST_USER", "Test@123")
TEST_PASS = os.environ.get("AUDIT_TEST_PASS", "Test@1234")
FACTORY_USER = "RLERLT"
FACTORY_PASS = os.environ.get("FACTORY_PASS", "Rahul")

# Actions exercised in this run (simulates UI button flows via audit-log/event + server routes)
EXPECTED_ACTIONS = [
    "Login",
    "Entered screen",
    "Exited screen",
    "Opened Quick Test",
    "Quick test started",
    "Test started",
    "Test finished",
    "Test aborted",
    "Test auto-aborted",
    "holder error",
    "check adaptor and holder",
    "Opened Load Recipe",
    "Loaded recipe",
    "Validation started",
    "Validation finished",
    "Validation aborted",
    "Entered USP 1 validation",
    "Logout",
    "Logout (inactivity timeout)",
    "Power interruption",
    "Test performed",
    "Adapter check error",
]


class RunResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)
        print("  OK  ", msg)

    def fail(self, msg: str) -> None:
        self.failed.append(msg)
        print("  FAIL", msg)

    def note_warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print("  WARN", msg)


def ts_ms() -> int:
    return int(time.time() * 1000)


class _Resp:
    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self.content = body

    def json(self):
        return json.loads(self.content.decode("utf-8")) if self.content else {}


class Client:
    def __init__(self):
        self._headers = {"Content-Type": "application/json"}

    def _request(self, method: str, path: str, body=None, params=None) -> _Resp:
        url = BASE + path
        if params:
            qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v is not None)
            if qs:
                url += ("&" if "?" in url else "?") + qs
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return _Resp(resp.status, resp.read())
        except urllib.error.HTTPError as e:
            return _Resp(e.code, e.read())

    def login(self, username: str, password: str) -> dict:
        r = self._request("POST", "/api/data/auth/login", {"username": username, "password": password})
        if r.status_code >= 400:
            raise RuntimeError(f"login HTTP {r.status_code}: {r.json()}")
        data = r.json()
        if not data.get("success") and "user" not in data:
            raise RuntimeError(f"login failed: {data}")
        return data.get("user") or data

    def logout(self, reason: str = "user") -> None:
        self._request("POST", "/api/data/auth/logout", {"reason": reason})

    def audit_event(self, action: str, details: str = "", **extra) -> _Resp:
        body = {
            "action": action,
            "details": details,
            "outcome": extra.pop("outcome", "success"),
            "eventType": extra.pop("eventType", "lifecycle"),
        }
        for k in ("entityType", "entityName", "entityId", "reason", "extra"):
            if k in extra:
                body[k] = extra[k]
        return self._request("POST", "/api/data/audit-log/event", body)

    def audit_log(self, **params) -> list:
        r = self._request("GET", "/api/data/audit-log", params=params or None)
        if r.status_code == 403:
            return []
        if r.status_code >= 400:
            raise RuntimeError(f"audit-log HTTP {r.status_code}")
        return (r.json() or {}).get("entries") or []

    def post_report(self, payload: dict) -> dict:
        r = self._request("POST", "/api/data/reports", payload)
        if r.status_code >= 400:
            raise RuntimeError(f"report HTTP {r.status_code}: {r.json()}")
        return r.json()

    def validation_start(self, mode: str) -> _Resp:
        return self._request("POST", "/api/hardware/validation/load/start", {"mode": mode})

    def adapter_check(self) -> dict:
        r = self._request("POST", "/api/hardware/adapter/check")
        return r.json() if r.content else {}

    def validation_stop(self) -> None:
        self._request("POST", "/api/hardware/validation/load/stop", {})


def entries_since(entries: list, since_ms: int, username: str | None = None) -> list:
    out = []
    for e in entries:
        if int(e.get("timestamp") or 0) < since_ms:
            continue
        if username and (e.get("user") or "").strip() != username:
            continue
        out.append(e)
    return out


def actions_in(entries: list) -> set:
    return {str(e.get("action") or "").strip() for e in entries}


def simulate_ui_flow(c: Client, res: RunResult) -> None:
    """Mirror script.js logAuditEvent calls for navigation + test/validation lifecycle."""
    c.audit_event("Entered screen", "Home", eventType="navigation")
    c.audit_event("Opened Quick Test", "Quick Test screen opened", eventType="navigation")
    c.audit_event("Entered screen", "Quick Test", eventType="navigation")
    c.audit_event("Quick test started", "Quick Test, USP 1, 10 step(s)", eventType="lifecycle", extra={"productName": "Quick Test"})
    c.audit_event("Entered screen", "Test Run", eventType="navigation")
    c.audit_event("Test started", "Quick Test, USP 1, 10 step(s)", eventType="lifecycle")
    c.audit_event("Test finished", "Test run completed, 3 step(s) recorded", eventType="lifecycle", extra={"completedSteps": 3})
    c.audit_event("Exited screen", "Test Run", eventType="navigation")
    c.audit_event("Opened Load Recipe", "Load Recipe list opened", eventType="navigation")
    c.audit_event(
        "Loaded recipe",
        "Demo Product, batch B001",
        entityType="recipe",
        entityName="Demo Product",
        extra={"productName": "Demo Product", "batchNumber": "B001"},
    )
    c.audit_event("Test aborted", "User aborted test run", eventType="lifecycle")
    c.audit_event("Test auto-aborted", "Adapter removed during test run", outcome="failed", extra={"stepIndex": 2})
    c.audit_event(
        "holder error",
        "Adapter check failed for test run",
        outcome="failed",
        entityType="hardware",
        entityName="adapter",
        extra={"expected": "usp1", "detected": "usp2"},
    )
    c.audit_event("Entered USP 1 validation", "USP 1 validation screen", eventType="navigation")
    c.audit_event("Validation started", "USP 1 validation run started", entityType="validation")
    c.audit_event("Validation finished", "USP 1 validation: Pass", entityType="validation", extra={"status": "Pass"})
    c.audit_event("Validation aborted", "USP 1 validation aborted by user", entityType="validation")
    c.audit_event(
        "check adaptor and holder",
        "Adapter check failed for USP 2 validation",
        outcome="failed",
        entityType="hardware",
        entityName="adapter",
        extra={"expected": "usp2", "detected": "usp1"},
    )


def verify_factory_suppression(c: Client, res: RunResult, since_ms: int) -> None:
    c.login(FACTORY_USER, FACTORY_PASS)
    r = c.audit_event("Test started", "Factory should not appear in audit DB")
    if r.status_code != 200:
        res.fail(f"Factory audit event HTTP {r.status_code}")
    else:
        res.ok("Factory audit event endpoint accepts POST (200)")
    c.logout("user")
    time.sleep(0.3)
    c.login(TEST_USER, TEST_PASS)
    entries = c.audit_log()
    factory_rows = [
        e
        for e in entries_since(entries, since_ms)
        if (e.get("user") or "").strip() == FACTORY_USER
        and str(e.get("action") or "") == "Test started"
    ]
    if factory_rows:
        res.fail(f"Factory actor logged Test started ({len(factory_rows)} row(s))")
    else:
        res.ok("Factory (RLERLT) Test started suppressed from audit log")


def verify_logout_variants(c: Client, res: RunResult, since_ms: int) -> None:
    """Manual logout via live API; inactivity via test_client (browser session-ui-reset clears live session)."""
    c.login(TEST_USER, TEST_PASS)
    c.logout("user")
    time.sleep(0.2)
    c.login(TEST_USER, TEST_PASS)
    entries = actions_in(entries_since(c.audit_log(), since_ms, TEST_USER))
    if "Logout" in entries:
        res.ok("Logout (manual) recorded on live API")
    else:
        res.fail("Missing Logout (manual)")

    inactivity_since = ts_ms() - 1000
    try:
        from app import app as flask_app

        tc = flask_app.test_client()
        lr = tc.post("/api/data/auth/login", json={"username": TEST_USER, "password": TEST_PASS})
        if lr.status_code != 200:
            res.fail(f"In-process login HTTP {lr.status_code}")
            return
        lo = tc.post("/api/data/auth/logout", json={"reason": "inactivity"})
        if lo.status_code != 200:
            res.fail(f"In-process inactivity logout HTTP {lo.status_code}")
            return
        import audit_service

        audit_service.init(
            {"STORAGE_DIR": APP_ROOT / "storage", "REPORTS_DIR": APP_ROOT / "reports"}
        )
        recent = {
            str(e.get("action") or "").strip()
            for e in audit_service.list_entries({"from": inactivity_since})
        }
        if "Logout (inactivity timeout)" in recent:
            res.ok("Logout (inactivity timeout) recorded (in-process logout route)")
        else:
            res.fail("Missing Logout (inactivity timeout) from logout route")
    except Exception as exc:
        res.fail(f"In-process inactivity logout test: {exc}")


def verify_power_interruption(res: RunResult, since_ms: int) -> None:
    import data_service
    import audit_service

    config = {"STORAGE_DIR": APP_ROOT / "storage", "REPORTS_DIR": APP_ROOT / "reports"}
    data_service.init(config)
    audit_service.init(config)

    flag = APP_ROOT / "storage" / "app_clean_stop.flag"
    if flag.exists():
        flag.unlink()

    user = {"username": TEST_USER, "role": "User", "name": TEST_USER}
    data_service.save_current_user(user)
    data_service.write_session_power_audit_pending(user)

    from app import _startup_session_power_audit

    _startup_session_power_audit()

    entries = audit_service.list_entries({"from": since_ms})
    pi_logout = [e for e in entries if e.get("action") == "Power interruption logout"]
    if pi_logout:
        res.ok(f"Power interruption logout logged ({len(pi_logout)} row(s))")
        details = (pi_logout[-1].get("details") or "").lower()
        if TEST_USER.lower() in details or "logged in" in details or "shutdown" in details:
            res.ok("Power interruption logout details mention session/shutdown")
        else:
            res.note_warn("Power interruption logout row present but details lack session wording")
    else:
        res.fail("Power interruption logout not logged after simulated unclean startup")


def verify_power_cut_report_recovery(res: RunResult) -> None:
    import shutil
    import tempfile

    import audit_service
    import data_service
    import print_service
    import report_service

    tmp_root = Path(tempfile.mkdtemp(prefix="kiosk-power-cut-"))
    storage = tmp_root / "storage"
    reports = tmp_root / "reports"
    audit_db = tmp_root / "db"
    storage.mkdir(parents=True)
    reports.mkdir(parents=True)
    audit_db.mkdir(parents=True)
    config = {
        "STORAGE_DIR": storage,
        "REPORTS_DIR": reports,
        "AUDIT_DB_DIR": audit_db,
        "APP_ROOT": APP_ROOT,
    }
    data_service.init(config)
    audit_service.init(config)
    report_service.init(config)
    print_service.init(config)

    import app as kiosk_app

    kiosk_app.STORAGE_DIR = storage
    kiosk_app.REPORTS_DIR = reports
    kiosk_app.AUDIT_DB_DIR = audit_db
    data_service.init(config)
    audit_service.init(config)
    report_service.init(config)
    print_service.init(config)
    startup_power_audit = kiosk_app._startup_session_power_audit

    since_ms = ts_ms() - 1000

    def _assert_recovered_report(report: dict, label: str, expect_type: str, expect_duration: int) -> bool:
        td = report.get("testData") or {}
        ok = True
        if report.get("type") != expect_type:
            res.fail(f"{label}: report type {report.get('type')!r} != {expect_type!r}")
            ok = False
        if str(report.get("status") or "") != "Completed":
            res.fail(f"{label}: status {report.get('status')!r} != Completed")
            ok = False
        if str(report.get("reportApprovalStatus") or "").lower() != "approved":
            res.fail(f"{label}: reportApprovalStatus not approved")
            ok = False
        if str(report.get("approvalRemarks") or "") != "power interruption":
            res.fail(f"{label}: approvalRemarks not power interruption")
            ok = False
        if str(report.get("approvedBy") or "") != "System":
            res.fail(f"{label}: approvedBy not System")
            ok = False
        if str(report.get("approvalPassFail") or "").upper() != "FAIL":
            res.fail(f"{label}: approvalPassFail not FAIL")
            ok = False
        if expect_type == "test" and str(td.get("status") or "").lower() != "completed":
            res.fail(f"{label}: testData.status not completed")
            ok = False
        if expect_type == "validation" and str(td.get("status") or "").lower() != "fail":
            res.fail(f"{label}: testData.status not Fail")
            ok = False
        dur = td.get("durationSeconds")
        if dur is None:
            dur = td.get("durationSec")
        try:
            dur_n = int(dur) if dur is not None else -1
        except (TypeError, ValueError):
            dur_n = -1
        if dur_n < expect_duration:
            res.fail(f"{label}: durationSeconds {dur!r} expected >= {expect_duration}")
            ok = False
        start = td.get("testStartTime") or td.get("validationStartTime")
        end = td.get("testEndTime") or td.get("validationEndTime") or report.get("completedAt")
        if not start or not end:
            res.fail(f"{label}: missing start/end times start={start!r} end={end!r}")
            ok = False
        elif expect_duration > 0 and str(start) == str(end):
            res.fail(f"{label}: start==end ({start!r}) despite duration {dur_n}")
            ok = False
        elif start and end and expect_duration > 0:
            try:
                from datetime import datetime as _dt
                sdt = _dt.fromisoformat(str(start).replace("Z", "+00:00")).replace(tzinfo=None)
                edt = _dt.fromisoformat(str(end).replace("Z", "+00:00")).replace(tzinfo=None)
                gap = int((edt - sdt).total_seconds())
                if gap < expect_duration:
                    res.fail(f"{label}: end-start={gap}s < expected duration {expect_duration}")
                    ok = False
            except Exception as exc:
                res.fail(f"{label}: could not parse start/end: {exc}")
                ok = False
        derived = report.get("reportDerived") or {}
        if expect_type == "test" and derived:
            try:
                if int(derived.get("durationSeconds") or -1) < expect_duration:
                    res.fail(f"{label}: reportDerived.durationSeconds not preserved")
                    ok = False
            except (TypeError, ValueError):
                res.fail(f"{label}: reportDerived.durationSeconds invalid")
                ok = False
        entries = audit_service.list_entries({"from": since_ms})
        pi = [e for e in entries if e.get("action") == "Power interruption"]
        if not pi:
            res.fail(f"{label}: missing Power interruption audit row")
            ok = False
        elif ok:
            res.ok(f"{label}: recovered report id {report.get('id')} with Power interruption audit")
        return ok

    def _run_recovery(checkpoint: dict, label: str, expect_type: str, expect_duration: int, *, leave_clean_flag: bool = False) -> None:
        for name in ("reports.json", "test_run.json", "session_power_audit_pending.json", "app_clean_stop.flag"):
            path = storage / name
            if path.exists():
                path.unlink()
        data_service.save_test_run_data(checkpoint)
        data_service.write_session_power_audit_pending({"username": TEST_USER, "role": "User"})
        if leave_clean_flag:
            data_service.touch_app_clean_stop_flag()
        data_service.init(config)

        startup_power_audit()
        reports_list = data_service.list_reports("all", include_pending=True)
        if len(reports_list) != 1:
            res.fail(f"{label}: expected 1 recovered report, got {len(reports_list)}")
            return
        _assert_recovered_report(reports_list[0], label, expect_type, expect_duration)

    test_cp = {
        "type": "test",
        "_checkpointPhase": "running",
        "_checkpointAt": "2026-08-12T10:00:30",
        "_checkpointSavedAt": "2026-08-12T10:00:30",
        "recipe": {
            "productName": "PowerCut Test",
            "batchNumber": "PC-1",
            "stepCount": 1,
            "steps": [],
        },
        "testData": {
            "status": "running",
            "productName": "PowerCut Test",
            "batchNumber": "PC-1",
            "elapsedSeconds": 30,
            "durationSeconds": 30,
            "testStartTime": "2026-08-12T10:00:00",
            "testEndTime": "2026-08-12T10:00:30",
        },
        "operatorName": TEST_USER,
        "operatedByUsername": TEST_USER,
    }
    _run_recovery(test_cp, "Test checkpoint recovery", "test", 30)

    # Collapsed start==end in checkpoint (field bug) must still reconstruct times from elapsed.
    collapsed_cp = {
        "type": "test",
        "_checkpointPhase": "running",
        "_checkpointAt": "2026-08-12T11:05:00",
        "_checkpointSavedAt": "2026-08-12T11:05:00",
        "recipe": {"productName": "Collapsed Times", "batchNumber": "CT-1", "stepCount": 1, "steps": []},
        "testData": {
            "status": "running",
            "productName": "Collapsed Times",
            "batchNumber": "CT-1",
            "elapsedSeconds": 90,
            "durationSeconds": 90,
            "testStartTime": "2026-08-12T11:05:00",
            "testEndTime": "2026-08-12T11:05:00",
        },
        "operatorName": TEST_USER,
        "operatedByUsername": TEST_USER,
    }
    _run_recovery(collapsed_cp, "Collapsed start==end reconstruction", "test", 90)

    # Leftover clean-stop flag must not drop an in-progress checkpoint.
    clean_flag_cp = dict(test_cp)
    clean_flag_cp["testData"] = dict(test_cp["testData"])
    clean_flag_cp["testData"]["productName"] = "CleanFlag Bypass"
    clean_flag_cp["recipe"] = dict(test_cp["recipe"])
    clean_flag_cp["recipe"]["productName"] = "CleanFlag Bypass"
    _run_recovery(
        clean_flag_cp,
        "Checkpoint recovery despite clean-stop flag",
        "test",
        30,
        leave_clean_flag=True,
    )

    val_cp = {
        "type": "validation",
        "_checkpointPhase": "running",
        "_checkpointAt": "2026-08-12T10:00:12",
        "testData": {
            "status": "running",
            "durationSec": 12,
            "durationSeconds": 12,
            "elapsedSeconds": 12,
            "validationStartTime": "2026-08-12T10:00:00",
            "testStartTime": "2026-08-12T10:00:00",
            "validationRuns": [
                {
                    "usp": "USP",
                    "rpm": 25,
                    "status": "Running",
                    "actualRotationCount": 5,
                    "expectedRotationCount": 100,
                    "durationSec": 12,
                    "validationStartTime": "2026-08-12T10:00:00",
                }
            ],
        },
        "operatorName": TEST_USER,
    }
    _run_recovery(val_cp, "Validation checkpoint recovery", "validation", 12)

    for name in ("reports.json", "test_run.json"):
        path = storage / name
        if path.exists():
            path.unlink()
    op_cp = {
        "type": "test",
        "_checkpointPhase": "aborted",
        "abortCause": "operator",
        "recipe": {"productName": "Op Abort", "batchNumber": "OA-1", "stepCount": 1, "steps": []},
        "testData": {"status": "aborted", "remarks": "Aborted", "abortCause": "operator"},
        "operatorName": TEST_USER,
    }
    data_service.save_test_run_data(op_cp)
    data_service.init(config)
    startup_power_audit()
    op_reports = data_service.list_reports("all", include_pending=True)
    if len(op_reports) != 1:
        res.fail(f"Operator abort recovery: expected 1 report, got {len(op_reports)}")
    else:
        op_report = op_reports[0]
        if str(op_report.get("status") or "") != "Aborted":
            res.fail(f"Operator abort recovery: status {op_report.get('status')!r} != Aborted")
        elif str(op_report.get("reportApprovalStatus") or "").lower() != "aborted":
            res.fail("Operator abort recovery: reportApprovalStatus not aborted")
        else:
            res.ok("Operator abort checkpoint stays Aborted")

    try:
        shutil.rmtree(tmp_root)
    except Exception:
        pass


def verify_hardware_routes(c: Client, res: RunResult, since_ms: int) -> None:
    c.login(TEST_USER, TEST_PASS)
    check = c.adapter_check()
    res.ok(f"Adapter check API ok={check.get('ok')}")
    for mode in ("usp1", "usp2"):
        r = c.validation_start(mode)
        if r.status_code == 400 and (r.json() or {}).get("error") == "adapter_mismatch":
            action = "holder error" if mode == "usp1" else "check adaptor and holder"
            res.ok(f"validation/load/start mode={mode} → adapter_mismatch (400)")
        elif r.status_code == 200:
            res.note_warn(f"validation/load/start mode={mode} succeeded (adapter matched hardware)")
            c.validation_stop()
        else:
            res.note_warn(f"validation/load/start mode={mode} → HTTP {r.status_code}: {(r.json() or {}).get('error')}")
    time.sleep(0.3)
    entries = actions_in(entries_since(c.audit_log(), since_ms, TEST_USER))
    if "holder error" in entries or "check adaptor and holder" in entries:
        res.ok("Server-side adapter/holder error action in audit log")
    else:
        res.note_warn("No USP adapter error from hardware (adapter may match device)")


def verify_report_audit(c: Client, res: RunResult, since_ms: int) -> None:
    c.login(TEST_USER, TEST_PASS)
    payload = {
        "name": "Audit verify test report",
        "type": "test",
        "recipe": {"productName": "Quick Test", "batchNumber": "AUDIT-1", "stepCount": 1, "steps": []},
        "testData": {
            "productName": "Quick Test",
            "batchNumber": "AUDIT-1",
            "status": "completed",
            "completedSteps": 1,
            "stepCount": 1,
            "stepResults": [],
        },
    }
    try:
        rep = c.post_report(payload)
        rid = rep.get("id")
        res.ok(f"Report created id={rid}")
        time.sleep(0.3)
        entries = entries_since(c.audit_log(), since_ms, TEST_USER)
        if any(e.get("action") == "Quick test performed" for e in entries):
            res.ok("Quick test performed audit on report save")
        elif any(e.get("action") == "Test performed" for e in entries):
            res.ok("Test performed audit on report save")
        else:
            res.fail("No Test performed / Quick test performed on report save")
    except Exception as exc:
        res.fail(f"Report create failed: {exc}")


def verify_pdf_html(res: RunResult, since_ms: int) -> None:
    import audit_service
    import data_service
    from app import _build_audit_trail_html

    config = {"STORAGE_DIR": APP_ROOT / "storage", "REPORTS_DIR": APP_ROOT / "reports"}
    data_service.init(config)
    audit_service.init(config)
    entries = audit_service.list_entries({"from": since_ms})
    factory = data_service.get_factory_settings() or {}
    html = _build_audit_trail_html(entries, {}, factory)
    required = ("Test started", "Validation finished", "Power interruption")
    missing = [a for a in required if a not in html]
    if "Logout (inactivity timeout)" in html or "Logout" in html:
        res.ok("Audit PDF HTML includes logout action(s)")
    else:
        missing.append("Logout")
    if not missing:
        res.ok("Audit PDF HTML includes new action labels")
    else:
        res.fail(f"Audit HTML missing actions: {missing}")


def verify_export_stage_endpoints(c: Client, res: RunResult) -> None:
    """Smoke-test compliance export staging endpoints."""
    try:
        r = c._request("POST", "/api/audit/export/stage", {"filters": {}})
        stage = r.json() if r.content else {}
        if stage.get("success") and stage.get("batchId"):
            res.ok("Audit export stage returns batchId")
        else:
            res.fail(f"Audit export stage failed: {stage}")
    except Exception as exc:
        res.fail(f"Audit export stage: {exc}")

    try:
        r = c._request("GET", "/api/data/reports", params={"filter": "all"})
        reports = r.json() if r.content else {}
        ids = [int(rpt["id"]) for rpt in (reports.get("reports") or [])[:1] if rpt.get("id")]
        if not ids:
            res.note_warn("No reports to test report export stage")
            return
        r2 = c._request("POST", "/api/reports/export/stage", {"report_ids": ids})
        stage = r2.json() if r2.content else {}
        if stage.get("success") and stage.get("batchId"):
            res.ok("Report export stage returns batchId")
        else:
            res.fail(f"Report export stage failed: {stage}")
    except Exception as exc:
        res.fail(f"Report export stage: {exc}")


def verify_purge_primitives(res: RunResult) -> None:
    import audit_service
    import data_service

    config = {"STORAGE_DIR": APP_ROOT / "storage", "REPORTS_DIR": APP_ROOT / "reports"}
    data_service.init(config)
    audit_service.init(config)
    batch = audit_service.stage_audit_export([999999], "tester", "approver")
    if batch.get("id"):
        res.ok("audit_service.stage_audit_export")
    confirmed = audit_service.confirm_audit_export_batch(batch["id"], "/tmp/test.pdf")
    if confirmed and confirmed.get("confirmedAt"):
        res.ok("audit_service.confirm_audit_export_batch")
    rb = data_service.stage_report_export([999998], "tester", "approver")
    if rb.get("id"):
        res.ok("data_service.stage_report_export")


def main() -> int:
    since_ms = ts_ms() - 5000
    res = RunResult()
    c = Client()

    print("=== Audit trail verification ===")
    print(f"API: {BASE}")
    print(f"User: {TEST_USER}")
    print()

    try:
        c.login(TEST_USER, TEST_PASS)
        res.ok("Login")
    except Exception as exc:
        res.fail(f"Login: {exc}")
        return 1

    verify_export_stage_endpoints(c, res)
    verify_purge_primitives(res)

    since_ms = ts_ms() - 1000
    simulate_ui_flow(c, res)
    verify_report_audit(c, res, since_ms)
    verify_logout_variants(c, res, since_ms)
    verify_hardware_routes(c, res, since_ms)

    factory_since = ts_ms() - 1000
    verify_factory_suppression(c, res, factory_since)

    power_since = ts_ms() - 1000
    verify_power_interruption(res, power_since)
    verify_power_cut_report_recovery(res)

    verify_pdf_html(res, since_ms - 120000)

    c.login(TEST_USER, TEST_PASS)
    all_entries = entries_since(c.audit_log(), since_ms, TEST_USER)
    found = actions_in(all_entries)
    print()
    print("--- Actions seen for test user since run ---")
    for a in sorted(found):
        print(" ", a)

    missing = [a for a in EXPECTED_ACTIONS if a not in found and a not in ("Login", "Power interruption", "Adapter check error")]
    if missing:
        res.note_warn(f"Simulated actions not all visible for {TEST_USER}: {missing}")

    print()
    print(f"Passed: {len(res.passed)}, Failed: {len(res.failed)}, Warnings: {len(res.warnings)}")
    if res.failed:
        for f in res.failed:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
