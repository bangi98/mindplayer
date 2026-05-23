# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0] — decorator-based framework integrations

### Changed (breaking)
- **Framework integrations are now per-endpoint decorators**, not
  middleware. All three frameworks expose the same `@traced` /
  `@traced(name="...")` API:
  - Flask: `from tracesnap.integrations.flask import traced`
  - Django: `from tracesnap.integrations.django import traced`
  - FastAPI: `from tracesnap.integrations.fastapi import configure, traced`
  Recording is gated on the `TRACESNAP_ENABLED=1` env var, so the
  decorator is a zero-cost no-op in production.
- Status code now reflects framework exceptions: DRF `ValidationError` →
  400, Starlette `HTTPException` → its `status_code`, etc. (previously
  the trace recorded 500 for any exception path).

### Removed (breaking)
- `tracesnap.integrations.flask.TraceSnap` (the Flask app extension).
- `tracesnap.integrations.django.RecorderMiddleware` and its
  `MIDDLEWARE`/`TRACESNAP` settings-based wiring.
- `tracesnap.integrations.fastapi.install()` and `TraceSnapMiddleware`.

### Migration
Per-request middleware → per-endpoint decorator. Before:

```python
# Flask 0.1.x
TraceSnap(app, output_dir="traces", source_files=[__file__])
```

After:

```python
# Flask 0.2.x
app.config["TRACESNAP"] = {"output_dir": "traces", "source_files": [__file__]}

@app.route("/checkout")
@traced
def checkout(): ...
```

The motivation: `sys.settrace` is too expensive to pay on every request,
and middleware traces flood the dashboard with infrastructure noise
(static files, schema endpoints, favicons). Decorators keep recording
surgical and intentional.

### Added
- `tracesnap.integrations.fastapi.configure(...)` — module-level config
  setter (FastAPI has no central settings object).
- Smoke tests for the Django and FastAPI decorators (both sync and async
  path operations).

## [0.1.0] — initial release

### Added
- Core recorder: `start_recording` / `stop_recording`, ContextVar-based
  per-context session.
- High-level API: `tracesnap.record(...)` as both context manager and
  decorator; `write_trace` / `load_trace` helpers.
- CLI: `tracesnap record` and `tracesnap view` (the latter spins up a
  stdlib `http.server` and opens the bundled players in the default
  browser).
- Three bundled players (HTML/JS, no JS dependencies):
  - Text view (`player.html`)
  - Flowchart simulator (`simulator.html`)
  - Call graph with click-to-details + zoom + draggable columns
    (`call_graph.html`)
- All three players auto-load via `?trace=<path>` URL parameter when
  served by `tracesnap view`.
- Framework integrations (pip extras): Flask (`tracesnap[flask]`),
  Django (`tracesnap[django]`), FastAPI (`tracesnap[fastapi]`).
- Trace format: `parent_seq` on every event, `structure_by_file`
  bundled in session, statement-level structure nodes for
  flowchart drawing.
- Configurable redaction via `redact_names=`.
- Outbound HTTP capture via monkey-patching `requests.Session.send`
  and `urllib.request.urlopen`.
- Examples for each framework + two standalone scripts
  (`sample_program.py`, `sample_complex.py`).
- Documentation: README + `docs/trace-format-v0.1.md`.
- Pytest suite: structure, record API, redaction, CLI, Flask
  integration smoke.

### Known limitations
- Recursion: player keys frames by stack position; recursive calls
  collide.
- In-place mutation isn't logged (use rebinding).
- No `httpx` / DB driver / socket capture yet.
- Async: per-task contextvars work; concurrent traced sub-tasks
  share a session.
- Exception events not yet emitted.
