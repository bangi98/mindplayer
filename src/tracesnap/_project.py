"""
Per-project identity for the trace library.

A trace is recorded *somewhere* — almost always inside a project. The library
is a single shared store (``~/.tracesnap``), but every record is stamped with a
``project`` name so the player can show one project at a time (and switch
between them) instead of mixing every project's traces together.

The project name comes from a ``.tracesnap.toml`` file at the project root — the
nearest one found by walking up from the working directory. If there is no
config, the name defaults to the basename of that directory.

    # .tracesnap.toml
    project = "my-app"

Zero-dependency by design: we only ever read/write the single ``project`` key,
so we parse it by hand rather than pull in a TOML library (``tomllib`` is 3.11+
and core tracesnap declares no runtime deps).
"""
import re
from pathlib import Path

CONFIG_NAME = ".tracesnap.toml"

# project = "name"  /  project = 'name'   (trailing comment tolerated)
_PROJECT_RE = re.compile(r"""^\s*project\s*=\s*(?:"([^"]*)"|'([^']*)')\s*(?:#.*)?$""")


def _dir(start=None):
    """The directory to reason about: ``start`` (its parent if it's a file),
    or the current working directory."""
    if start is None:
        return Path.cwd()
    p = Path(start).resolve()
    return p.parent if p.is_file() else p


def find_config(start=None):
    """Return the nearest ``.tracesnap.toml`` at or above ``start`` (default
    CWD), or ``None`` if there is none up to the filesystem root."""
    base = _dir(start)
    for d in (base, *base.parents):
        cfg = d / CONFIG_NAME
        if cfg.is_file():
            return cfg
    return None


def project_root(start=None):
    """Directory that defines the current project: the one holding the nearest
    config, or ``start``/CWD itself when there is no config."""
    cfg = find_config(start)
    return cfg.parent if cfg is not None else _dir(start)


def _parse_project(text):
    for line in text.splitlines():
        m = _PROJECT_RE.match(line)
        if m:
            return (m.group(1) or m.group(2) or "").strip() or None
    return None


def read_config_project(cfg_path):
    """Read the ``project`` value out of a config file, or ``None``."""
    try:
        return _parse_project(Path(cfg_path).read_text(encoding="utf-8"))
    except OSError:
        return None


def current_project(start=None):
    """Resolve the project name for ``start`` (default CWD).

    Uses the nearest ``.tracesnap.toml``'s ``project`` key; falls back to the
    basename of the project root. Always returns a non-empty string.
    """
    cfg = find_config(start)
    if cfg is not None:
        name = read_config_project(cfg)
        if name:
            return name
        return cfg.parent.name or "default"   # config present but key unusable
    return project_root(start).name or "default"


def write_config(root, project):
    """Write ``project`` into ``<root>/.tracesnap.toml``, creating the file or
    updating the existing ``project`` line in place. Returns the config path."""
    cfg = Path(root) / CONFIG_NAME
    line = f'project = "{project}"'
    if cfg.exists():
        try:
            lines = cfg.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for i, ln in enumerate(lines):
            if _PROJECT_RE.match(ln):
                lines[i] = line
                break
        else:
            lines.insert(0, line)
        text = "\n".join(lines) + "\n"
    else:
        text = f"# tracesnap project config\n{line}\n"
    cfg.write_text(text, encoding="utf-8")
    return cfg


def init_project(start=None, name=None):
    """Create (or update) a config at ``start``/CWD itself — not a parent — so
    running ``init`` deliberately establishes a project boundary here. Defaults
    the name to the folder name. Returns ``(config_path, project_name)``."""
    here = _dir(start)
    name = (name or "").strip() or here.name or "default"
    return write_config(here, name), name


def set_project(name, start=None):
    """Set the project name, writing to the nearest existing config or creating
    one at the project root. Returns ``(config_path, name)``."""
    name = (name or "").strip() or _dir(start).name or "default"
    cfg = find_config(start)
    root = cfg.parent if cfg is not None else _dir(start)
    return write_config(root, name), name
