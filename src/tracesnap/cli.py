"""
Command-line interface: `tracesnap record / view / list / rename / delete`.
"""
import argparse
import ast
import json
import sys
from pathlib import Path

from . import __version__, _project, library
from ._recorder import start_recording, stop_recording
from .api import write_trace
from .server import DEFAULT_PORT, serve


# ---------------------------------------------------------------------------
# Source-file discovery
# ---------------------------------------------------------------------------
_DISCOVERY_LIMIT = 50


def _discover_local_sources(entry):
    """Starting from `entry`, BFS-walk imports and return the set of .py
    files reachable via `import X` / `from X import …` that live under
    `entry.parent`. Stdlib / site-packages / anything outside the entry
    directory is intentionally excluded so the recorder doesn't trace
    framework noise.
    """
    root = entry.parent.resolve()
    found = [entry.resolve()]
    seen = {found[0]}
    queue = [found[0]]
    while queue and len(found) < _DISCOVERY_LIMIT:
        current = queue.pop(0)
        try:
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Resolve module-relative bits ("from .pkg import name" / "from pkg import name").
                # We only care about discovering files inside `root`, so try both the
                # module name itself and each imported name (which could be a submodule
                # in the same package).
                module = node.module or ""
                if module:
                    names.append(module)
                for alias in node.names:
                    if module:
                        names.append(f"{module}.{alias.name}")
                    else:
                        names.append(alias.name)
            for dotted in names:
                resolved = _resolve_module(dotted, root)
                if resolved is None:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                found.append(resolved)
                queue.append(resolved)
                if len(found) >= _DISCOVERY_LIMIT:
                    break
    return found


def _resolve_module(dotted_name, root):
    """Map a dotted module name to a .py file under `root`, if any.
    Tries `root/foo/bar.py` and `root/foo/bar/__init__.py`."""
    parts = dotted_name.split(".")
    candidate = root.joinpath(*parts).with_suffix(".py")
    if candidate.is_file():
        try:
            candidate = candidate.resolve()
        except OSError:
            return None
        if root in candidate.parents or candidate.parent == root:
            return candidate
    pkg_init = root.joinpath(*parts, "__init__.py")
    if pkg_init.is_file():
        try:
            pkg_init = pkg_init.resolve()
        except OSError:
            return None
        if root in pkg_init.parents or pkg_init.parent == root:
            return pkg_init
    return None


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------
def cmd_record(args):
    target = Path(args.path).resolve()
    if not target.exists():
        print(f"error: {target} not found", file=sys.stderr)
        return 2
    src = target.read_text()

    redact = None
    if args.redact:
        redact = {name.strip() for name in args.redact.split(",") if name.strip()}

    out_path = Path(args.out).resolve() if args.out else None
    structure_path = None
    if out_path:
        structure_path = out_path.with_suffix(".structure.json") if args.structure_out is None \
                         else Path(args.structure_out).resolve()

    project = (args.project or "").strip() or _project.current_project(str(target))

    discovered = _discover_local_sources(target)
    source_files = [str(p) for p in discovered]
    start_recording(trace_id=args.id, kind=args.kind,
                    source_files=source_files, redact_names=redact)
    code = compile(src, str(target), "exec")
    exec_error = None
    # Run the script the way `python script.py ...` would: as __main__, with
    # its own sys.argv. This lets recorded scripts read command-line arguments
    # (and runs their `if __name__ == "__main__":` block).
    saved_argv = sys.argv
    sys.argv = [str(target), *args.script_args]
    try:
        exec(code, {"__name__": "__main__", "__file__": str(target)})
    except BaseException as e:                 # noqa: BLE001
        exec_error = e
    finally:
        sys.argv = saved_argv
        trace = stop_recording()

    if out_path:
        write_trace(trace, out_path)
        structure = trace["session"].get("structure_by_file", {}).get(str(target))
        if structure is not None:
            with open(structure_path, "w", encoding="utf-8") as f:
                json.dump({"version": "0.1", "source_path": str(target),
                           "nodes": structure}, f, indent=2)

    # Save to the library unless --no-library is passed.
    meta = None
    if not args.no_library:
        structure_obj = None
        primary_structure = trace["session"].get("structure_by_file", {}).get(str(target))
        if primary_structure is not None:
            structure_obj = {"version": "0.1", "source_path": str(target),
                             "nodes": primary_structure}
        meta = library.add(trace, name=args.name or args.id,
                           source=str(target), structure_json=structure_obj,
                           project=project)

    events = trace["events"]
    counts = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1

    out_stream = sys.stderr if exec_error else sys.stdout
    if exec_error is not None:
        print(f"tracesnap: traced code raised {type(exec_error).__name__}: {exec_error}",
              file=sys.stderr)
        print(f"tracesnap: partial trace saved ({len(events)} events)", file=sys.stderr)
    else:
        print(f"tracesnap: recorded {len(events)} events", file=out_stream)
    print(f"tracesnap: event types: {counts}", file=out_stream)
    if args.script_args:
        print(f"tracesnap: script argv {args.script_args}", file=out_stream)
    if len(source_files) > 1:
        print(f"tracesnap: traced {len(source_files)} files "
              f"(entrypoint + {len(source_files) - 1} sibling)", file=out_stream)
    if out_path:
        print(f"tracesnap: wrote {out_path}", file=out_stream)
    if meta:
        print(f"tracesnap: library id  {meta['id']}", file=out_stream)
        print(f"tracesnap: library name {meta['name']!r}", file=out_stream)
        print(f"tracesnap: project      {meta.get('project') or '(none)'}", file=out_stream)
        print(f"tracesnap: open it with:  tracesnap view {meta['id']}", file=out_stream)
    return 1 if exec_error else 0


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------
def cmd_view(args):
    trace_arg = args.path
    target_id = None
    if trace_arg is not None:
        target_id, resolved = library.resolve(trace_arg)
        if resolved is None and target_id is None:
            print(f"error: no library entry or file matching {trace_arg!r}", file=sys.stderr)
            return 2
        trace_arg = str(resolved) if resolved else None
    serve(trace_path=trace_arg, target_id=target_id, view=args.view,
          port=args.port, open_browser=not args.no_browser,
          scan_root=args.scan_root)
    return 0


# ---------------------------------------------------------------------------
# list / rename / delete
# ---------------------------------------------------------------------------
def cmd_list(args):
    project = getattr(args, "project", None)
    records = library.list_traces(project=project)
    if not records:
        root = library.library_root()
        scope = f" for project {project!r}" if project else ""
        print(f"(no saved records yet{scope} in {root})")
        print("Run `tracesnap record <file.py>` to create one.")
        return 0
    # Compact aligned table
    w_id = max(len(r["id"]) for r in records)
    w_name = max(len(r["name"]) for r in records)
    w_proj = max([len(r.get("project") or "-") for r in records] + [len("PROJECT")])
    print(f"{'ID'.ljust(w_id)}  {'NAME'.ljust(w_name)}  {'PROJECT'.ljust(w_proj)}  "
          f"CREATED               EVENTS  KIND")
    for r in records:
        proj = (r.get("project") or "-").ljust(w_proj)
        print(f"{r['id'].ljust(w_id)}  {r['name'].ljust(w_name)}  {proj}  "
              f"{r['created']:<20}  {r['event_count']:>6}  {r['kind']}")
    return 0


def cmd_init(args):
    cfg, name = _project.init_project(name=args.name)
    print(f"tracesnap: project {name!r}")
    print(f"tracesnap: wrote {cfg}")
    print("New records made from this directory will be tagged with this project.")
    return 0


def cmd_project(args):
    if args.name:
        cfg, name = _project.set_project(args.name)
        print(f"tracesnap: project set to {name!r}")
        print(f"tracesnap: wrote {cfg}")
        return 0
    name = _project.current_project()
    cfg = _project.find_config()
    if cfg is not None:
        print(f"{name}  ({cfg})")
    else:
        print(f"{name}  (defaulted to folder name — no {_project.CONFIG_NAME} found)")
        print("Run `tracesnap init` to make it explicit.")
    return 0


def cmd_rename(args):
    m = library.rename(args.id, args.name)
    if m is None:
        print(f"error: no record with id {args.id!r}", file=sys.stderr)
        return 2
    print(f"tracesnap: renamed {args.id} -> {m['name']!r}")
    return 0


def cmd_delete(args):
    if not args.force:
        confirm = input(f"delete {args.id!r}? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            print("aborted")
            return 0
    ok = library.delete(args.id)
    if not ok:
        print(f"error: no record with id {args.id!r}", file=sys.stderr)
        return 2
    print(f"tracesnap: deleted {args.id}")
    return 0


def cmd_version(_args):
    print(f"tracesnap {__version__}")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(prog="tracesnap",
        description="Record once, replay anywhere — a time-travel debugger for Python.")
    parser.add_argument("--version", action="store_true", help="print version and exit")

    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("record", help="Run a Python file under instrumentation and save a trace.")
    r.add_argument("path", help="Python file to run.")
    r.add_argument("--out", default=None,
                   help="Also write the trace to this path (in addition to the library).")
    r.add_argument("--structure-out", default=None,
                   help="Where to write structure.json (default: alongside --out).")
    r.add_argument("--id", default="trace",
                   help="trace_id stored inside the trace (default: 'trace').")
    r.add_argument("--name", default=None,
                   help="Display name for the library entry (default: same as --id).")
    r.add_argument("--no-library", action="store_true",
                   help="Skip saving this trace to the library.")
    r.add_argument("--kind", default="script",
                   help="session.kind value (default: 'script').")
    r.add_argument("--redact", default=None,
                   help="Comma-separated extra variable names to redact.")
    r.add_argument("--project", default=None,
                   help="Project to file this record under (default: from "
                        ".tracesnap.toml, else the current folder name).")
    r.add_argument("script_args", nargs="*", metavar="ARG",
                   help="Arguments passed to the script as sys.argv[1:]. Put "
                        "them after a literal `--`, e.g. "
                        "`tracesnap record app.py -- --verbose input.csv`.")
    r.set_defaults(func=cmd_record)

    v = sub.add_parser("view", help="Open a trace in the player. Without args, browse the library.")
    v.add_argument("path", nargs="?", default=None,
                   help="Library id, exact name, or path to a trace.json. Omit to browse all.")
    v.add_argument("--view", choices=("home", "text", "simulator", "graph", "call_graph",
                                       "event_graph", "events", "record"),
                   default=None,
                   help="Which page to open first. Default: 'home' when browsing the "
                        "library, 'call_graph' when a specific trace is given.")
    v.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"Port for the local server (default: {DEFAULT_PORT}; "
                        "falls back to a random free port if taken; pass 0 to always randomize).")
    v.add_argument("--no-browser", action="store_true",
                   help="Don't auto-open the default browser.")
    v.add_argument("--scan-root", default=None,
                   help="Directory the 'New record' page scans for .py files "
                        "(default: CWD where this command was started).")
    v.set_defaults(func=cmd_view)

    ls = sub.add_parser("list", help="List saved records in the library.")
    ls.add_argument("--project", default=None,
                    help="Only list records filed under this project.")
    ls.set_defaults(func=cmd_list)

    ini = sub.add_parser("init",
        help="Create a .tracesnap.toml in this directory to name the project.")
    ini.add_argument("--name", default=None,
                     help="Project name (default: this folder's name).")
    ini.set_defaults(func=cmd_init)

    pj = sub.add_parser("project",
        help="Show the current project, or set it with a name argument.")
    pj.add_argument("name", nargs="?", default=None,
                    help="New project name. Omit to print the current one.")
    pj.set_defaults(func=cmd_project)

    rn = sub.add_parser("rename", help="Rename a saved record.")
    rn.add_argument("id", help="Library id (from `tracesnap list`).")
    rn.add_argument("name", help="New display name.")
    rn.set_defaults(func=cmd_rename)

    rm = sub.add_parser("delete", help="Delete a saved record.")
    rm.add_argument("id", help="Library id.")
    rm.add_argument("-f", "--force", action="store_true", help="Skip confirmation.")
    rm.set_defaults(func=cmd_delete)

    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    # Everything after a literal `--` is handed to the recorded script as its
    # own sys.argv, never parsed as a tracesnap option. (argparse's native `--`
    # handling is unreliable with subparsers, so we split it off ourselves.)
    passthrough = []
    if "--" in argv:
        idx = argv.index("--")
        argv, passthrough = argv[:idx], argv[idx + 1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.script_args = passthrough + list(getattr(args, "script_args", None) or [])
    if args.version:
        return cmd_version(args)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
