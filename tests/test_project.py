"""Tests for per-project identity and project-scoped library queries."""
import pytest

from tracesnap import _project, library


# ---------------------------------------------------------------------------
# _project: resolving the current project
# ---------------------------------------------------------------------------
def test_defaults_to_folder_name(tmp_path):
    proj = tmp_path / "my-cool-app"
    proj.mkdir()
    assert _project.current_project(proj) == "my-cool-app"
    assert _project.find_config(proj) is None


def test_config_overrides_folder_name(tmp_path):
    proj = tmp_path / "repo-dir"
    proj.mkdir()
    (proj / ".tracesnap.toml").write_text('project = "shop-api"\n')
    assert _project.current_project(proj) == "shop-api"


def test_single_quotes_and_trailing_comment(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".tracesnap.toml").write_text("project = 'svc'   # the api\n")
    assert _project.current_project(proj) == "svc"


def test_config_found_by_walking_up(tmp_path):
    root = tmp_path / "root"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (root / ".tracesnap.toml").write_text('project = "top"\n')
    assert _project.current_project(nested) == "top"
    assert _project.find_config(nested) == root / ".tracesnap.toml"


def test_resolves_from_a_file_path(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".tracesnap.toml").write_text('project = "fromfile"\n')
    script = proj / "script.py"
    script.write_text("x = 1\n")
    assert _project.current_project(script) == "fromfile"


def test_empty_project_key_falls_back_to_dir_name(tmp_path):
    proj = tmp_path / "named-dir"
    proj.mkdir()
    (proj / ".tracesnap.toml").write_text('project = ""\n')
    assert _project.current_project(proj) == "named-dir"


# ---------------------------------------------------------------------------
# _project: writing config
# ---------------------------------------------------------------------------
def test_init_creates_config_with_folder_default(tmp_path):
    proj = tmp_path / "auto-named"
    proj.mkdir()
    cfg, name = _project.init_project(start=proj)
    assert name == "auto-named"
    assert cfg.read_text(encoding="utf-8").strip().splitlines()[-1] == 'project = "auto-named"'
    assert _project.current_project(proj) == "auto-named"


def test_set_project_updates_existing_line_in_place(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".tracesnap.toml").write_text(
        "# my config\nproject = \"old\"\nother = 1\n")
    cfg, name = _project.set_project("new", start=proj)
    assert name == "new"
    text = cfg.read_text(encoding="utf-8")
    assert 'project = "new"' in text
    assert "old" not in text
    assert "other = 1" in text   # untouched


# ---------------------------------------------------------------------------
# library: project stamping + filtering
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACESNAP_HOME", str(tmp_path / "lib"))
    return tmp_path


def _fake_trace(events=3):
    return {
        "version": "0.1",
        "trace_id": "demo",
        "session": {"kind": "script", "entry": "demo.py:<module>"},
        "events": [{"seq": i, "type": "line", "line": 1} for i in range(events)],
    }


def test_add_stamps_explicit_project(tmp_library):
    m = library.add(_fake_trace(), name="a", project="alpha")
    assert m["project"] == "alpha"
    assert library.list_traces()[0]["project"] == "alpha"


def test_add_resolves_project_from_cwd(tmp_library, monkeypatch):
    proj = tmp_library / "beta-proj"
    proj.mkdir()
    monkeypatch.chdir(proj)
    m = library.add(_fake_trace(), name="b")
    assert m["project"] == "beta-proj"


def test_list_traces_filters_by_project(tmp_library):
    library.add(_fake_trace(), name="a", project="alpha")
    library.add(_fake_trace(), name="b", project="beta")
    library.add(_fake_trace(), name="c", project="alpha")

    alpha = library.list_traces(project="alpha")
    assert {m["name"] for m in alpha} == {"a", "c"}
    assert len(library.list_traces(project="beta")) == 1
    assert len(library.list_traces()) == 3          # no filter -> all
    assert library.list_traces(project="nope") == []


def test_list_projects_counts(tmp_library):
    library.add(_fake_trace(), project="alpha")
    library.add(_fake_trace(), project="alpha")
    library.add(_fake_trace(), project="beta")
    assert library.list_projects() == {"alpha": 2, "beta": 1}
