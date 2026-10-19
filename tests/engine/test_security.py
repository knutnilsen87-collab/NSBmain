import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from nsb_engine.security import AccessToken, AuditLog, MasterKey, Paths, Vault  # noqa: E402
from nsb_engine.server import create_app  # noqa: E402
from nsb_engine.sessions import SessionStore  # noqa: E402
from nsb_engine.streaming import SAMPLE_RATE, Word  # noqa: E402

WS = "ws://127.0.0.1:8765/v1/stream"


class Backend:
    def transcribe(self, audio, prompt=None, hotwords=None):
        n = min(4, int(len(audio) / SAMPLE_RATE / 0.4))
        return [Word(["Han", "nektet", "straffskyld", "punktum"][i], i * 0.4, i * 0.4 + 0.35, 0.9) for i in range(n)]


def pcm(seconds):
    return (np.ones(int(seconds * SAMPLE_RATE)) * 300).astype("<i2").tobytes()


@pytest.fixture
def app(tmp_path):
    return create_app(Backend(), model_label="t", data_root=tmp_path, use_dpapi=False, retention_days=30)


def client(app, token=True, **kw):
    headers = {"Authorization": f"Bearer {app.state.token.value}"} if token else {}
    headers.update(kw.pop("headers", {}))
    return TestClient(app, base_url="http://127.0.0.1:8765", headers=headers, **kw)


def dictate(app, start: dict, seconds=2.0):
    c = client(app)
    with c.websocket_connect(f"{WS}?token={app.state.token.value}") as ws:
        ws.send_text(json.dumps({"type": "start", **start}))
        for _ in range(int(seconds / 0.25)):
            ws.send_bytes(pcm(0.25))
        ws.send_text(json.dumps({"type": "end"}))
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] in ("final", "error"):
                if m["type"] == "error":
                    continue
                return m


# ---------- tilgang


def test_calls_without_token_are_refused_and_logged(app):
    c = client(app, token=False)
    assert c.get("/v1/health").status_code == 200  # åpen, ingen hemmeligheter
    assert c.post("/v1/transcribe", content=b"x").status_code == 401
    assert c.get("/v1/sessions").status_code == 401
    bad = client(app, token=False, headers={"Authorization": "Bearer feil"})
    assert bad.get("/v1/sessions").status_code == 401
    assert [e["action"] for e in app.state.audit.entries()].count("auth.denied") == 3


def test_websocket_requires_token(app):
    c = client(app)
    with pytest.raises(WebSocketDisconnect), c.websocket_connect(WS) as ws:
        ws.receive_text()
    with pytest.raises(WebSocketDisconnect), c.websocket_connect(f"{WS}?token=feil") as ws:
        ws.receive_text()


def test_foreign_web_page_cannot_use_the_stream(app):
    c = client(app)
    url = f"{WS}?token={app.state.token.value}"
    with pytest.raises(WebSocketDisconnect), c.websocket_connect(url, headers={"origin": "https://ondsinnet.example"}) as ws:
        ws.receive_text()
    with c.websocket_connect(url, headers={"origin": "http://127.0.0.1:8765"}) as ws:
        ws.send_text(json.dumps({"type": "end"}))
        assert json.loads(ws.receive_text())["type"] == "final"


def test_dns_rebinding_host_is_refused(app):
    c = TestClient(app, base_url="http://ondsinnet.example", headers={"Authorization": f"Bearer {app.state.token.value}"})
    assert c.get("/v1/sessions").status_code == 421


def test_allowed_origin_gets_cors(tmp_path):
    app = create_app(Backend(), data_root=tmp_path, use_dpapi=False, allowed_origins=["http://localhost:5173"])
    c = client(app)
    ok = c.options("/v1/sessions", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.options("/v1/sessions", headers={"Origin": "https://ondsinnet.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


@pytest.mark.skipif(__import__("os").name == "nt", reason="filrettigheter er POSIX")
def test_token_is_stable_and_private(tmp_path):
    paths = Paths(tmp_path).ensure()
    a, b = AccessToken(paths), AccessToken(paths)
    assert a.value == b.value and len(a.value) >= 40
    assert oct(paths.token.stat().st_mode)[-3:] == "600"
    assert a.check(a.value) and not a.check("") and not a.check(None)


# ---------- lagring


def test_nothing_is_stored_without_store_flag(app, tmp_path):
    final = dictate(app, {})
    assert "session_id" not in final
    assert not list((tmp_path / "sessions").iterdir())


def test_store_requires_consent(app):
    final = dictate(app, {"store": True})
    assert "session_id" not in final


def test_stored_session_is_encrypted_and_readable_with_token(app, tmp_path):
    final = dictate(app, {"store": True, "consent": True, "case_ref": "24-123456MED-OTIR"})
    sid = final["session_id"]
    files = {p.name for p in (tmp_path / "sessions").iterdir()}
    assert {f"{sid}.key", f"{sid}.audio.bin", f"{sid}.transcript.bin", f"{sid}.meta.json"} <= files
    raw = (tmp_path / "sessions" / f"{sid}.transcript.bin").read_bytes()
    assert b"nektet" not in raw and b"straffskyld" not in raw
    c = client(app)
    body = c.get(f"/v1/sessions/{sid}").json()
    assert "nektet" in body["text"] and body["meta"]["case_ref"] == "24-123456MED-OTIR"
    wav = c.get(f"/v1/sessions/{sid}/audio")
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"
    listed = c.get("/v1/sessions").json()["sessions"]
    assert [s["id"] for s in listed] == [sid] and "text" not in listed[0]


def test_correction_and_deletion_are_audited(app, tmp_path):
    sid = dictate(app, {"store": True, "consent": True})["session_id"]
    c = client(app, headers={"X-NSB-User": "advokat.hansen"})
    assert c.put(f"/v1/sessions/{sid}/transcript", json={"text": "Han nektet straffskyld."}).status_code == 200
    assert c.get(f"/v1/sessions/{sid}").json()["corrected"]["text"] == "Han nektet straffskyld."
    assert c.delete(f"/v1/sessions/{sid}").status_code == 204
    assert c.get(f"/v1/sessions/{sid}").status_code == 404
    assert not list((tmp_path / "sessions").glob(f"{sid}*"))
    actions = [(e["action"], e["actor"].split("/")[-1]) for e in app.state.audit.entries(sid)]
    assert ("session.stored", actions[0][1]) == actions[0]
    assert ("session.corrected", "user:advokat.hansen") in actions
    assert ("session.read", "user:advokat.hansen") in actions
    assert ("session.deleted", "user:advokat.hansen") in actions
    assert c.get("/v1/audit/verify").json() == {"valid": True, "first_broken_line": None}


def test_client_can_shorten_but_not_extend_retention(app):
    store = app.state.store
    short = dictate(app, {"store": True, "consent": True, "retention_days": 2})
    long = dictate(app, {"store": True, "consent": True, "retention_days": 365})
    days = lambda m: (datetime.fromisoformat(m.expires) - datetime.fromisoformat(m.created)).days  # noqa: E731
    assert days(store.meta(short["session_id"])) == 2
    assert days(store.meta(long["session_id"])) == 30


def test_expired_sessions_are_purged(tmp_path):
    paths = Paths(tmp_path).ensure()
    master = MasterKey(paths, use_dpapi=False)
    audit = AuditLog(paths, master)
    store = SessionStore(paths, Vault(paths, master), audit, retention_days=7)
    meta = store.save(pcm16=pcm(1.0), words=[], text="x", actor="t", consent=True)
    assert store.purge_expired(now=datetime.now(timezone.utc) + timedelta(days=6)) == []
    assert store.purge_expired(now=datetime.now(timezone.utc) + timedelta(days=8)) == [meta.id]
    assert store.list() == []
    assert audit.entries(meta.id)[-1]["details"]["reason"] == "expired"


def test_deleting_the_key_makes_leftover_data_unreadable(tmp_path):
    paths = Paths(tmp_path).ensure()
    master = MasterKey(paths, use_dpapi=False)
    vault = Vault(paths, master)
    vault.create("abcdefghijklmnopqrstuv")
    vault.put("abcdefghijklmnopqrstuv", "audio", b"hemmelig lyd")
    leftover = (paths.sessions / "abcdefghijklmnopqrstuv.audio.bin").read_bytes()
    vault.destroy("abcdefghijklmnopqrstuv")
    (paths.sessions / "abcdefghijklmnopqrstuv.audio.bin").write_bytes(leftover)  # som om filen ble gjenopprettet
    with pytest.raises(KeyError):
        vault.get("abcdefghijklmnopqrstuv", "audio")


def test_tampered_ciphertext_is_rejected(tmp_path):
    from cryptography.exceptions import InvalidTag

    paths = Paths(tmp_path).ensure()
    vault = Vault(paths, MasterKey(paths, use_dpapi=False))
    vault.create("abcdefghijklmnopqrstuv")
    vault.put("abcdefghijklmnopqrstuv", "transcript", b"tekst")
    p = paths.sessions / "abcdefghijklmnopqrstuv.transcript.bin"
    data = bytearray(p.read_bytes())
    data[-1] ^= 1
    p.write_bytes(bytes(data))
    with pytest.raises(InvalidTag):
        vault.get("abcdefghijklmnopqrstuv", "transcript")


def test_invalid_session_ids_are_rejected(app):
    c = client(app)
    assert c.get("/v1/sessions/..%2F..%2Faccess_token").status_code == 404
    assert c.delete("/v1/sessions/x").status_code == 404


# ---------- innsynslogg


def test_audit_log_detects_edits_and_removed_lines(tmp_path):
    paths = Paths(tmp_path).ensure()
    log = AuditLog(paths, MasterKey(paths, use_dpapi=False))
    for i in range(3):
        log.record("session.read", actor="a", session=f"s{i}")
    assert log.verify() == (True, None)
    lines = paths.audit.read_text(encoding="utf-8").splitlines()
    edited = json.loads(lines[1])
    edited["actor"] = "noen andre"
    paths.audit.write_text("\n".join([lines[0], json.dumps(edited), lines[2]]) + "\n", encoding="utf-8")
    assert log.verify() == (False, 2)
    paths.audit.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert log.verify() == (False, 2)


def test_audit_chain_cannot_be_rebuilt_without_the_master_key(tmp_path):
    import hashlib

    paths = Paths(tmp_path).ensure()
    log = AuditLog(paths, MasterKey(paths, use_dpapi=False))
    log.record("session.deleted", actor="a", session="s")
    entry = json.loads(paths.audit.read_text(encoding="utf-8"))
    entry["actor"] = "falsk"
    body = {k: v for k, v in entry.items() if k != "hash"}
    entry["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    paths.audit.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert log.verify() == (False, 1)


def test_audit_never_contains_dictated_text(app):
    dictate(app, {"store": True, "consent": True})
    raw = app.state.paths.audit.read_text(encoding="utf-8")
    assert "nektet" not in raw and "straffskyld" not in raw


def test_server_refuses_non_loopback_host_without_flag():
    from nsb_engine.server import main

    with pytest.raises(SystemExit):
        main(["--model", "x", "--host", "0.0.0.0"])


def test_admin_cli_verifies_and_deletes(tmp_path, capsys):
    from nsb_engine.admin import main

    app = create_app(Backend(), data_root=tmp_path, use_dpapi=False)
    sid = dictate(app, {"store": True, "consent": True})["session_id"]
    assert main(["--data-dir", str(tmp_path), "verify"]) == 0
    assert main(["--data-dir", str(tmp_path), "delete", sid]) == 0
    capsys.readouterr()
    assert main(["--data-dir", str(tmp_path), "sessions"]) == 0
    assert capsys.readouterr().out == ""
    assert app.state.audit.entries(sid)[-1]["actor"] == "admin"


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI finnes bare på Windows")
def test_master_key_is_protected_with_dpapi_on_windows(tmp_path):
    paths = Paths(tmp_path).ensure()
    first = MasterKey(paths, use_dpapi=True)
    assert paths.master_key.read_bytes().startswith(b"DPAPI1:")
    assert first.key not in paths.master_key.read_bytes()  # filen inneholder ikke nøkkelen i klartekst
    assert MasterKey(paths, use_dpapi=True).key == first.key


# ---------- paring for EVIDA


def evida_app(tmp_path):
    return create_app(Backend(), data_root=tmp_path, use_dpapi=False, allowed_origins=["http://127.0.0.1:5173"])


def test_pairing_gives_token_to_allowed_origin_once(tmp_path):
    app = evida_app(tmp_path)
    c = client(app, token=False)
    code = app.state.pairing["code"]
    r = c.post("/v1/pair", json={"code": code}, headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 200 and r.json()["token"] == app.state.token.value
    again = c.post("/v1/pair", json={"code": code}, headers={"Origin": "http://127.0.0.1:5173"})
    assert again.status_code == 410
    assert [e["action"] for e in app.state.audit.entries()].count("pair.succeeded") == 1


def test_pairing_refuses_other_origins_and_wrong_codes(tmp_path):
    app = evida_app(tmp_path)
    c = client(app, token=False)
    code = app.state.pairing["code"]
    assert c.post("/v1/pair", json={"code": code}, headers={"Origin": "https://ondsinnet.example"}).status_code == 403
    assert c.post("/v1/pair", json={"code": code}).status_code == 403  # uten Origin: ikke en nettleser fra EVIDA
    for _ in range(5):
        assert c.post("/v1/pair", json={"code": "00000000" if code != "00000000" else "11111111"},
                      headers={"Origin": "http://127.0.0.1:5173"}).status_code == 401
    # Etter fem feil er paring stengt, også med riktig kode.
    assert c.post("/v1/pair", json={"code": code}, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 410


def test_paired_origin_can_stream(tmp_path):
    app = evida_app(tmp_path)
    c = client(app)
    url = f"{WS}?token={app.state.token.value}&user=evida"
    with c.websocket_connect(url, headers={"origin": "http://127.0.0.1:5173"}) as ws:
        ws.send_text(json.dumps({"type": "end"}))
        assert json.loads(ws.receive_text())["type"] == "final"
    assert any(e["actor"].endswith("/user:evida") for e in app.state.audit.entries())
