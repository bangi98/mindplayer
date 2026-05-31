# tracesnap

**Record once, replay anywhere.** A time-travel debugger for Python with a
visual browser-based player. Run your code under instrumentation, get a
self-contained JSON trace, then scrub through it line-by-line in three
views (text, simulator, call graph) — no re-execution.

> Status: alpha. Stdlib-only core, plug-and-play integrations for
> Flask, Django, and FastAPI.

---

## Why

`pdb` lets you pause once. `print()` litters your code. Profilers count
nanoseconds but don't show you state. tracesnap captures every line,
every assignment, every branch, and every outbound HTTP call into one
JSON file you can replay, share in a PR, or attach to a bug report.

## Install

```bash
pip install tracesnap                # core + CLI + bundled players
pip install tracesnap[flask]         # + Flask integration
pip install tracesnap[django]        # + Django middleware
pip install tracesnap[fastapi]       # + FastAPI integration
pip install tracesnap[all]           # everything above
```

Requires Python 3.9+. The core has zero runtime dependencies.

## Quickstart

Record a script:

```bash
tracesnap record examples/sample_complex.py
```

Open it in your browser:

```bash
tracesnap view
```

That's it. `tracesnap view` (no args) opens the **library** — a list of
every recording you've made — and you can pick one to replay. To jump
straight into a specific trace:

```bash
tracesnap view <id>          # use the id printed by `record`
tracesnap view trace.json    # or a saved file
```

You'll get a three-view player:

- **Text view** — current step, call stack, full per-variable history.
- **Simulator** — animated flowchart with loops as cycle boxes,
  branches with the taken arm tagged ✓, variable chips that flash when
  changed.
- **Call graph** — every function as a node, edges labelled with args
  going in and return values coming back; click a node for per-call
  details.

All three views consume the same trace and switch via the header
buttons.

## Library use

Three equally-valid entry points, same underlying engine:

```python
import tracesnap

# 1) Context manager (preferred for explicit scope)
with tracesnap.record(trace_id="demo") as out:
    do_stuff()
# out.path        -> "trace.json"  (when path= is passed)
# out.event_count
# out.trace       -> the trace dict in memory

# 2) Decorator (records every call to the wrapped function)
@tracesnap.record(trace_id="checkout")
def checkout(items, coupon):
    ...

# 3) Imperative (lowest level; what the integrations use under the hood)
tracesnap.start_recording(trace_id="x", source_files=[__file__])
try:
    do_stuff()
finally:
    trace = tracesnap.stop_recording()
    tracesnap.write_trace(trace, "trace.json")
```

## Projects

The library lives in one place (`~/.tracesnap/` by default), shared across
every project on your machine — but each record is tagged with a **project**
so they don't all blur together. The project name comes from a
`.tracesnap.toml` at your project root, defaulting to the folder name:

```bash
tracesnap init                  # writes .tracesnap.toml (project = "<folder>")
tracesnap init --name shop-api  # …or name it yourself
tracesnap project               # print the current project
tracesnap project shop-api      # rename it later
```

```toml
# .tracesnap.toml
project = "shop-api"
```

`tracesnap view` opens the home page already filtered to the current project
(the directory you ran it from); a dropdown switches to any other project or to
**All projects**. From the CLI, `tracesnap list --project shop-api` and
`tracesnap record … --project shop-api` scope the same way. Records created
before this feature show up under **All projects** (project "unknown").

## Framework integrations

All three frameworks expose the same `@traced` decorator. Decorate only
the endpoints you actually want to record — middleware-style blanket
capture is intentionally **not** offered, because `sys.settrace` is too
expensive to pay on every request and most endpoints aren't worth
recording. Recording is gated on the `TRACESNAP_ENABLED=1` environment
variable, so the decorator is a no-op in production.

### Flask

```python
from flask import Flask
from tracesnap.integrations.flask import traced

app = Flask(__name__)
app.config["TRACESNAP"] = {
    "output_dir": "traces",
    "source_files": [__file__],
}

@app.route("/checkout")
@traced
def checkout():
    ...
```

Stack `@traced` *below* `@app.route(...)` (closer to the function).

### Django

```python
# settings.py
TRACESNAP = {
    "output_dir": "traces",
    "source_files": [str(BASE_DIR / "myapp" / "views.py")],
}

# views.py
from tracesnap.integrations.django import traced

@traced
def checkout(request):
    ...

# DRF ViewSet action
class ProductViewSet(viewsets.ModelViewSet):
    @traced
    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        ...
```

For inherited DRF actions (`list`, `retrieve`, `create`, `update`,
`partial_update`, `destroy`), override and call `super()`:

```python
class ProductViewSet(viewsets.ModelViewSet):
    @traced
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
```

### FastAPI

```python
from fastapi import FastAPI, Request
from tracesnap.integrations.fastapi import configure, traced

app = FastAPI()
configure(output_dir="traces", source_files=[__file__])

@app.get("/checkout")
@traced
async def checkout(request: Request):
    ...
```

Stack `@traced` *below* `@app.get(...)`. Declare a `request: Request`
parameter on the view so the trace can capture method/path (FastAPI only
injects it if asked). Works on both `def` and `async def` handlers.

Async note: `sys.settrace` is per-thread; `contextvars` are per-task.
For one handler per request (the common case) this works correctly.
Concurrent `asyncio.gather(...)` of multiple traced sub-tasks within a
single request boundary share the same recording session — not
recommended for production. Document/test your specific use.

## CLI reference

```
tracesnap record  PATH [--out FILE] [--id NAME] [--name NAME]
                       [--redact NAMES] [--no-library] [--kind KIND]
                       [--structure-out FILE] [--project NAME]

tracesnap view    [PATH] [--view text|simulator|graph|events|home|record]
                         [--port PORT] [--no-browser] [--scan-root DIR]

tracesnap list                    # show the library  [--project NAME]
tracesnap rename  ID NEW_NAME
tracesnap delete  ID [-f]

tracesnap init                    # name this project ([--name NAME])
tracesnap project [NAME]          # show or set the current project

tracesnap --version
```

### `record`

Runs the given `.py` under instrumentation, auto-discovers sibling
modules it imports, and saves the trace to the on-disk library (under
`~/.tracesnap/` by default). Useful flags:

- `--out FILE` — also write a standalone copy to disk.
- `--id NAME` — short identifier stored inside the trace and used as the
  library id (default: `"trace"`).
- `--name NAME` — human-readable display name for the library entry.
- `--redact NAMES` — comma-separated extra variable names to redact, on
  top of the built-in set (`password`, `token`, `secret`,
  `authorization`, `api_key`).
- `--no-library` — skip saving to the library.
- `--project NAME` — file this record under a project (default: from
  `.tracesnap.toml`, else the current folder name). See [Projects](#projects).

### `view`

Starts a tiny stdlib `http.server` (no extra deps), copies the bundled
player HTMLs into a tmpdir, and opens your default browser.

**Port behavior:**

- Default port is **`8765`** — stable across runs, so bookmarks and
  open tabs survive a restart.
- If `8765` is taken, tracesnap falls back to a random free port and
  prints a notice.
- `--port N` pins to your own choice (same fallback applies).
- `--port 0` always picks a random free port.

**Other useful flags:**

- `--view NAME` — start on a specific page (`text`, `simulator`,
  `graph`, `events`, `home`, or `record`). Default: `home` when
  browsing the library, `call_graph` when a specific trace is given.
- `--no-browser` — print the URL but don't auto-open the browser
  (useful over SSH or in containers).
- `--scan-root DIR` — directory the in-browser "New record" page walks
  when offering scripts to run (default: CWD).

## What gets recorded

Every event carries `seq`, `ts`, `depth`, `line`, `parent_seq` plus
type-specific fields:

| type      | fields                                                                          |
|-----------|---------------------------------------------------------------------------------|
| `call`    | `func`, `args` (each value with `repr`, `type`, `redacted`)                     |
| `line`    | `func`                                                                          |
| `assign`  | `var`, `scope`, `value`, `prev`, `change_index`                                 |
| `branch`  | `node_id`, `taken` (`"if"` / `"else"`)                                          |
| `loop`    | `node_id`, `iteration` (0-based)                                                |
| `return`  | `func`, `value`                                                                 |
| `extcall` | `kind`, `verb`, `target`, `status`, `duration_ms`, `started_ts`, `ended_ts`     |

Values are `{repr, type, id, truncated, redacted}`. `repr` is capped at
120 chars (`truncated: true` if hit). Variables named `password`,
`token`, `secret`, `authorization`, `api_key` get `<redacted>` — both as
function args and as locals. Extend the set via `redact_names=` on any
entry point or `--redact` on the CLI.

`parent_seq` links events into a tree:

- Inside a `for`/`while` body, every event has `parent_seq` pointing at
  the current iteration's `loop` event.
- Inside an `if`/`else` arm, every event points at the `branch` event.
- Top-level events in a function have `parent_seq: null`.
- A `call` event's `parent_seq` is the **caller's** context at the call
  site (so a call made inside an `if` arm points at the branch event in
  the caller, not at the new frame).

Full spec: [`docs/trace-format-v0.1.md`](docs/trace-format-v0.1.md).

## Examples

The [`examples/`](examples/) directory has runnable samples:

```bash
tracesnap record examples/sample_program.py    # straight-line script
tracesnap record examples/sample_complex.py    # branches, loops, recursion
tracesnap record examples/sample_pipeline.py   # multi-stage data flow
tracesnap record examples/sample_backtrace.py  # exception path
python  examples/flask_app.py                  # Flask demo (needs [flask])
python  examples/fastapi_app.py                # FastAPI demo (needs [fastapi])
python  examples/django_app.py                 # Django demo (needs [django])
```

For framework demos, install the extra first:

```bash
pip install -e .[flask]
python examples/flask_app.py
# then in another terminal:
curl http://127.0.0.1:5050/checkout
tracesnap view              # browse the request traces
```

## Known issues / edges

- **Recursion** — the player keys frames by stack position, so recursive
  calls collide. Roadmap item: per-call `frame_id`.
- **Assign attribution is one line late** — `sys.settrace` fires before
  a line runs; we attribute the diff to the previous line. Documented
  in the trace-format spec.
- **Value-change vs assignment** — we log value *changes*, so in-place
  mutation like `xs.append(y)` doesn't emit. Use rebinding
  (`xs = xs + [y]`) to see growth.
- **`extcall` scope** — only `requests.Session.send` and
  `urllib.request.urlopen` are wrapped. `httpx`, DB drivers, and stdlib
  `socket` are not (yet).
- **Async** — per-task `contextvars` work; per-task
  `threading.settrace` does not (yet). Concurrent traced sub-tasks
  share the same session.

## Development

```bash
git clone https://github.com/bangi98/mindplayer
cd mindplayer
pip install -e .[dev]

python -m pytest tests/        # run the test suite
python -m build                # build a wheel
```

The repo directory is still called `mindplayer` (the original project
name) — the published package is `tracesnap`.

## Roadmap

- SQLite backend for traces > ~10k events (single-trace decision; JSON
  stays default).
- `depends_on` field on `assign` events → true data-flow graphs in the
  call-graph view.
- `exception` events on unwind.
- `httpx` + DB driver `extcall` capture.
- Per-task `threading.settrace` for parallel-async support.

## License

MIT — see [LICENSE](LICENSE).
