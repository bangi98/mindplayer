"""Smoke test for the Django @traced decorator. Skipped if Django isn't installed.

Django's `settings.configure()` is global per-process, so we configure once at
module load and mutate `settings.TRACESNAP` per test.
"""
import json
import os
from pathlib import Path

import pytest

django = pytest.importorskip("django")


HERE = os.path.abspath(__file__)


def _setup_django():
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            SECRET_KEY="test-key",
            ROOT_URLCONF="tests.test_django_integration",
            ALLOWED_HOSTS=["*"],
            MIDDLEWARE=[],
            INSTALLED_APPS=[],
            TRACESNAP={"output_dir": "traces", "source_files": [HERE]},
        )
        django.setup()


_setup_django()

from django.http import JsonResponse  # noqa: E402
from django.urls import path  # noqa: E402

from tracesnap.integrations.django import traced  # noqa: E402


def helper(items):
    total = 0
    for x in items:
        total = total + x
    return total


@traced
def sum_view(request):
    return JsonResponse({"total": helper([1, 2, 3])})


def silent_view(request):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("sum", sum_view),
    path("silent", silent_view),
]


@pytest.fixture
def configured(tmp_path, monkeypatch):
    from django.conf import settings

    out_dir = tmp_path / "traces"
    monkeypatch.setattr(
        settings, "TRACESNAP", {"output_dir": str(out_dir), "source_files": [HERE]}
    )
    return out_dir


def test_traced_view_records_a_trace(configured, monkeypatch):
    from django.test import Client

    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    resp = Client().get("/sum")
    assert resp.status_code == 200
    assert resp.json() == {"total": 6}

    files = list(configured.glob("*.json"))
    assert len(files) == 1
    trace = json.loads(files[0].read_text())
    assert trace["session"]["kind"] == "request"
    assert trace["session"]["request"]["status"] == 200
    assert trace["session"]["request"]["method"] == "GET"
    assert trace["session"]["request"]["path"] == "/sum"
    funcs = {e.get("func") for e in trace["events"] if e["type"] == "call"}
    assert "sum_view" in funcs
    assert "helper" in funcs


def test_undecorated_view_produces_no_trace(configured, monkeypatch):
    from django.test import Client

    monkeypatch.setenv("TRACESNAP_ENABLED", "1")
    resp = Client().get("/silent")
    assert resp.status_code == 200
    assert not configured.exists() or list(configured.glob("*.json")) == []


def test_decorator_is_noop_without_env_var(configured, monkeypatch):
    from django.test import Client

    monkeypatch.delenv("TRACESNAP_ENABLED", raising=False)
    resp = Client().get("/sum")
    assert resp.status_code == 200
    assert not configured.exists() or list(configured.glob("*.json")) == []
