"""Smoke test for the FastAPI @traced decorator. Skipped if FastAPI/httpx aren't installed."""
import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")  # required by fastapi.testclient


def _build_app(tmp_path: Path):
    app_py = tmp_path / "fastapi_app_under_test.py"
    app_py.write_text(
        """
import os
from fastapi import FastAPI
from tracesnap.integrations.fastapi import configure, traced

app = FastAPI()
configure(output_dir=os.environ['TRACE_DIR'], source_files=[__file__])

def helper(items):
    total = 0
    for x in items:
        total = total + x
    return total

from fastapi import Request

@app.get('/sum')
@traced
def sum_endpoint(request: Request):
    return {'total': helper([1, 2, 3])}

@app.get('/silent')
def silent_endpoint():
    return {'ok': True}

@app.get('/async_sum')
@traced
async def async_sum_endpoint(request: Request):
    return {'total': helper([4, 5, 6])}
"""
    )
    import importlib.util
    import sys

    if "fastapi_app_under_test" in sys.modules:
        del sys.modules["fastapi_app_under_test"]
    spec = importlib.util.spec_from_file_location("fastapi_app_under_test", str(app_py))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fastapi_app_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_traced_sync_endpoint_records_a_trace(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    mod = _build_app(tmp_path)

    client = TestClient(mod.app)
    resp = client.get("/sum")
    assert resp.status_code == 200
    assert resp.json() == {"total": 6}

    files = list(out_dir.glob("*.json"))
    assert len(files) == 1
    trace = json.loads(files[0].read_text())
    assert trace["session"]["kind"] == "request"
    assert trace["session"]["request"]["status"] == 200
    assert trace["session"]["request"]["method"] == "GET"
    funcs = {e.get("func") for e in trace["events"] if e["type"] == "call"}
    assert "sum_endpoint" in funcs
    assert "helper" in funcs


def test_traced_async_endpoint_records_a_trace(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    mod = _build_app(tmp_path)

    client = TestClient(mod.app)
    resp = client.get("/async_sum")
    assert resp.status_code == 200
    assert resp.json() == {"total": 15}

    files = list(out_dir.glob("*.json"))
    assert len(files) == 1
    trace = json.loads(files[0].read_text())
    assert trace["session"]["request"]["status"] == 200
    funcs = {e.get("func") for e in trace["events"] if e["type"] == "call"}
    assert "async_sum_endpoint" in funcs


def test_undecorated_endpoint_produces_no_trace(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    mod = _build_app(tmp_path)

    client = TestClient(mod.app)
    resp = client.get("/silent")
    assert resp.status_code == 200

    assert not out_dir.exists() or list(out_dir.glob("*.json")) == []


def test_decorator_is_noop_without_env_var(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.delenv("TRACESNAP_ENABLED", raising=False)
    mod = _build_app(tmp_path)

    client = TestClient(mod.app)
    resp = client.get("/sum")
    assert resp.status_code == 200

    assert not out_dir.exists() or list(out_dir.glob("*.json")) == []
