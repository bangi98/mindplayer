"""Smoke tests for the CLI (record subcommand)."""
import json
import os
import subprocess
import sys
import textwrap


def test_cli_record(tmp_path):
    script = tmp_path / "demo.py"
    script.write_text(textwrap.dedent("""
        def f(x):
            return x + 1
        out = f(2)
    """).lstrip())
    out = tmp_path / "trace.json"
    cmd = [sys.executable, "-m", "tracesnap.cli", "record", str(script),
           "--out", str(out), "--id", "cli-test"]
    res = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ})
    assert res.returncode == 0, res.stderr
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["trace_id"] == "cli-test"
    assert data["events"][0]["type"] == "call"


def test_cli_record_passes_script_args(tmp_path):
    out = tmp_path / "argv.txt"
    script = tmp_path / "prog.py"
    script.write_text(textwrap.dedent(f"""
        import sys, pathlib
        pathlib.Path(r"{out}").write_text("|".join(sys.argv))
    """).lstrip())
    cmd = [sys.executable, "-m", "tracesnap.cli", "record", str(script),
           "--no-library", "--id", "args-test", "--", "alpha", "beta"]
    res = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ})
    assert res.returncode == 0, res.stderr
    parts = out.read_text().split("|")
    assert parts[0].endswith("prog.py")           # argv[0] is the script itself
    assert parts[1:] == ["alpha", "beta"]


def test_cli_record_runs_script_as_main(tmp_path):
    """A `__main__` guard fires, just like `python script.py`."""
    out = tmp_path / "ran.txt"
    script = tmp_path / "prog.py"
    script.write_text(textwrap.dedent(f"""
        import sys, pathlib
        if __name__ == "__main__":
            pathlib.Path(r"{out}").write_text(sys.argv[1])
    """).lstrip())
    cmd = [sys.executable, "-m", "tracesnap.cli", "record", str(script),
           "--no-library", "--", "hello"]
    res = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ})
    assert res.returncode == 0, res.stderr
    assert out.read_text() == "hello"


def test_coerce_args_string_and_list():
    from tracesnap import server
    assert server._coerce_args(None) == []
    assert server._coerce_args("") == []
    assert server._coerce_args("--verbose input.csv") == ["--verbose", "input.csv"]
    assert server._coerce_args('--name "two words"') == ["--name", "two words"]
    assert server._coerce_args(["a", "b"]) == ["a", "b"]
    # Unbalanced quotes fall back to a plain split rather than raising.
    assert server._coerce_args('a "b') == ["a", '"b']


def test_cli_version():
    res = subprocess.run([sys.executable, "-m", "tracesnap.cli", "--version"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "tracesnap" in res.stdout
