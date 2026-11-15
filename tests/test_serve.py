"""planted serve (gpt-researcher custom retriever) and the planted CLI; all network mocked."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import importlib

import planted.baselines as baselines_mod
from contracts.schemas import DefenseOut, GuardResult
from planted import serve as serve_mod

# the module, not planted.guard (= the exported guard function)
guard_mod = importlib.import_module("planted.guard")
ROOT = Path(__file__).resolve().parents[1]
HAVE_BANK = (ROOT / "data" / "pages" / "main" / "index.jsonl").exists()
needs_bank = pytest.mark.skipif(not HAVE_BANK, reason="no page bank")
QID = "pl-support-009"
HIDDEN = ("planted", "campaign_id", "asserted_answer", "label", "tier", "source_hedge")


@pytest.fixture
def client(monkeypatch):
    for key in ("TAVILY_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def no_network(*a, **kw):
        raise AssertionError("unexpected real HTTP call")

    monkeypatch.setattr(httpx, "post", no_network)
    monkeypatch.setattr(httpx, "get", no_network)
    return TestClient(serve_mod.create_app())


def _stub_guard(monkeypatch):
    def nie(*a, **kw):
        raise NotImplementedError("defense 'guard' not implemented yet")
    monkeypatch.setattr(guard_mod, "guard", nie)
    monkeypatch.setattr(baselines_mod, "apply_defense", nie)


def _fake_guard(monkeypatch):
    def annotate(query, results, lang="en"):
        rs = [{**r, "cluster_id": i % 2, "guard_score": 0.5} for i, r in enumerate(results)]
        return GuardResult(results=rs, system_note="Answer X: 6 pages / 1 origin",
                           warnings=["DATA_VOID: <2 independent origins"], hedge_floor="may")

    monkeypatch.setattr(guard_mod, "guard", annotate)
    monkeypatch.setattr(baselines_mod, "apply_defense",
                        lambda name, q, r, lang: DefenseOut(**annotate(q, r, lang).model_dump()))


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


TAVILY = {"results": [{"url": f"https://site{i}.example/a", "title": f"T{i}", "content": f"snippet {i}",
                       "raw_content": f"full text {i}", "score": 0.9} for i in range(3)]}


def _check_format(items):
    assert isinstance(items, list) and items
    for it in items:
        assert set(it) == {"url", "raw_content"}
        assert it["url"].startswith("https://") and isinstance(it["raw_content"], str)


# --------------------------------------------------------------------------- /health
def test_health_reports_guard_stub(client, monkeypatch):
    _stub_guard(monkeypatch)
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "guard_available": False}
    _fake_guard(monkeypatch)
    assert client.get("/health").json()["guard_available"] is True


# --------------------------------------------------------------------------- mock modes
@needs_bank
def test_mock_mode_returns_ten_items_without_hidden_fields(client):
    r = client.get("/search", params={"query": "support number", "mode": "mock", "qid": QID, "k": 3})
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 10
    _check_format(items)
    assert len({it["url"] for it in items}) == 10
    blob = json.dumps(items)
    for f in HIDDEN:
        assert f'"{f}"' not in blob
    assert all(it["url"].split("/")[2].endswith(".example") for it in items)


@needs_bank
def test_mock_errors(client):
    assert client.get("/search", params={"mode": "mock"}).status_code == 400  # no qid
    assert client.get("/search", params={"mode": "mock", "qid": "nope"}).status_code == 404
    assert client.get("/search", params={"mode": "bogus", "qid": QID}).status_code == 400
    assert client.get("/search", params={"mode": "mock", "qid": QID, "bank": "../outside"}).status_code == 400


@needs_bank
def test_mock_guard_501_while_stub(client, monkeypatch):
    _stub_guard(monkeypatch)
    r = client.get("/search", params={"mode": "mock_guard", "qid": QID})
    assert r.status_code == 501 and r.json() == {"detail": "Guard not implemented yet"}


@needs_bank
def test_mock_guard_with_fake_guard(client, monkeypatch):
    _fake_guard(monkeypatch)
    r = client.get("/search", params={"mode": "mock_guard", "qid": QID, "k": 3})
    assert r.status_code == 200, r.text
    items = r.json()
    _check_format(items)
    first = items[0]["raw_content"]
    assert first.startswith("Source analysis: Answer X: 6 pages / 1 origin")
    assert "DATA_VOID" in first
    assert all("[cluster_id=" in it["raw_content"] and "guard_score=0.5]" in it["raw_content"] for it in items)


# --------------------------------------------------------------------------- real-web modes
def test_passthrough_503_without_keys(client):
    r = client.get("/search", params={"query": "q", "mode": "passthrough"})
    assert r.status_code == 503 and "TAVILY_API_KEY" in r.json()["detail"]


def test_passthrough_tavily(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json)
        return _Resp(TAVILY)

    monkeypatch.setattr(httpx, "post", fake_post)
    r = client.get("/search", params={"query": "capital of nowhere", "mode": "passthrough"})
    assert r.status_code == 200, r.text
    items = r.json()
    _check_format(items)
    assert seen["url"] == serve_mod.TAVILY_URL and seen["json"]["query"] == "capital of nowhere"
    assert items[0] == {"url": "https://site0.example/a", "raw_content": "T0\nfull text 0"}


def test_passthrough_brave(client, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    payload = {"web": {"results": [{"url": "https://b.example/x", "title": "B", "description": "desc"}]}}
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _Resp(payload))
    r = client.get("/search", params={"query": "q", "mode": "passthrough"})
    assert r.status_code == 200 and r.json() == [{"url": "https://b.example/x", "raw_content": "B\ndesc"}]


def test_guard_mode(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp(TAVILY))
    _stub_guard(monkeypatch)
    r = client.get("/search", params={"query": "q", "mode": "guard"})
    assert r.status_code == 501 and r.json()["detail"] == "Guard not implemented yet"
    _fake_guard(monkeypatch)
    r = client.get("/search", params={"query": "q", "mode": "guard"})
    assert r.status_code == 200
    items = r.json()
    assert items[0]["raw_content"].startswith("Source analysis:")
    assert "[cluster_id=0, guard_score=0.5]" in items[0]["raw_content"]


def test_search_api_failure_is_502(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    def boom(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert client.get("/search", params={"query": "q", "mode": "passthrough"}).status_code == 502


# --------------------------------------------------------------------------- package + CLI
def test_package_exports():
    import planted

    assert planted.__version__ == "0.1.0"
    for name in ("guard", "apply_defense", "MockEngine", "make_episode_id"):
        assert callable(getattr(planted, name))


def test_cli_guard(tmp_path, monkeypatch, capsys):
    from planted.cli import main

    f = tmp_path / "r.json"
    f.write_text(json.dumps([{"url": "https://a.example/x", "title": "A", "snippet": "s",
                              "content": "c", "rank": 1}]), encoding="utf-8")
    _stub_guard(monkeypatch)
    assert main(["guard", "--query", "Q", "--results", str(f)]) == 1
    assert "Guard not implemented yet" in capsys.readouterr().err
    _fake_guard(monkeypatch)
    assert main(["guard", "--query", "Q", "--results", str(f)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["system_note"].startswith("Answer X") and out["results"][0]["cluster_id"] == 0


def test_cli_run_delegates_to_run_py(monkeypatch):
    from planted.cli import main

    if not HAVE_BANK:
        pytest.skip("no page bank")
    monkeypatch.chdir(ROOT)
    assert main(["run", "--arm", "A", "--dry-run", "--limit", "1"]) == 0
