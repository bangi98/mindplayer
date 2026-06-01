# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.2.2] - 2026-06-01

### Fixed
- **Top-level exceptions are now captured.** Exceptions raised in a recorded
  script's `<module>` frame (e.g. a crash at module top level) were never
  recorded as `exception` events, so the simulator showed "0 exceptions" and
  the trace's event-type counts had no `exception` key. The recorder now
  installs a minimal exception-only trace on `<module>` frames, capturing
  top-level raises while still keeping module-level line/assign/return
  statements out of the trace.

## [0.2.1] - 2026-06-01

### Added
- **Project-scoped library.** Every record is now stamped with a `project`
  name so traces from different projects no longer mix together. The name comes
  from a `.tracesnap.toml` (`project = "..."`) at the project root, falling back
  to the folder name. New commands: `tracesnap init` (write the config,
  defaulting to the folder name) and `tracesnap project [name]` (show or set it).
  `tracesnap record` takes `--project`, and `tracesnap list` takes `--project`
  plus shows a PROJECT column.
- The player home page gained a **project dropdown** that defaults to the
  current project (the directory `tracesnap view` ran in) with an
  "All projects" option. New API: `GET /api/projects` and a `?project=` filter
  on `GET /api/traces`.
- **Command-line arguments for recorded scripts.** `tracesnap record app.py --
  --verbose input.csv` passes everything after `--` to the script as its
  `sys.argv`. The "New record" page gained an **Arguments** field for the same.

### Changed
- Recorded scripts now run as `__main__` (previously `__traced__`), so a
  script's `if __name__ == "__main__":` block executes — `tracesnap record
  script.py` now behaves like `python script.py`.

### Fixed
- `tracesnap.__version__` was stuck at `0.1.0`; it now tracks the released
  version.

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
