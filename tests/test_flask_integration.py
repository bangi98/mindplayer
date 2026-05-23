"""Smoke test for the Flask @traced decorator. Skipped if Flask isn't installed."""
import json
import os
from pathlib import Path

import pytest

flask = pytest.importorskip("flask")


def _build_app(tmp_path: Path):
    """Write a Flask app to a tmp file and import it, so @traced has a
    real source file in the recording scope."""
    app_py = tmp_path / "app_under_test.py"
    app_py.write_text(
        """
import os
from flask import Flask, jsonify
from tracesnap.integrations.flask import traced

app = Flask(__name__)
app.config['TRACESNAP'] = {
    'output_dir': os.environ['TRACE_DIR'],
    'source_files': [__file__],
}

def helper(items):
    total = 0
    for x in items:
        total = total + x
    return total

@app.route('/sum')
@traced
def sum_endpoint():
    return jsonify({'total': helper([1, 2, 3])})

@app.route('/silent')
def silent_endpoint():
    # NOT decorated — must not produce a trace.
    return jsonify({'ok': True})
"""
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location("app_under_test", str(app_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_traced_endpoint_records_a_trace(tmp_path, monkeypatch):
    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    mod = _build_app(tmp_path)

    client = mod.app.test_client()
    resp = client.get("/sum")
    assert resp.status_code == 200
    assert resp.get_json() == {"total": 6}

    files = list(out_dir.glob("*.json"))
    assert len(files) == 1
    trace = json.loads(files[0].read_text())
    assert trace["session"]["kind"] == "request"
    assert trace["session"]["request"]["status"] == 200
    assert trace["session"]["request"]["method"] == "GET"
    assert trace["session"]["request"]["path"] == "/sum"
    funcs = {e.get("func") for e in trace["events"] if e["type"] == "call"}
    assert "sum_endpoint" in funcs
    assert "helper" in funcs


def test_undecorated_endpoint_produces_no_trace(tmp_path, monkeypatch):
    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    mod = _build_app(tmp_path)

    client = mod.app.test_client()
    resp = client.get("/silent")
    assert resp.status_code == 200

    assert not out_dir.exists() or list(out_dir.glob("*.json")) == []


def test_decorator_is_noop_without_env_var(tmp_path, monkeypatch):
    out_dir = tmp_path / "traces"
    monkeypatch.setenv("TRACE_DIR", str(out_dir))
    monkeypatch.delenv("TRACESNAP_ENABLED", raising=False)
    mod = _build_app(tmp_path)

    client = mod.app.test_client()
    resp = client.get("/sum")
    assert resp.status_code == 200

    assert not out_dir.exists() or list(out_dir.glob("*.json")) == []
