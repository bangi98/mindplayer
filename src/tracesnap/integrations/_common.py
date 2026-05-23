"""Internal helpers shared by the per-framework `@traced` decorators.

This module is intentionally not part of the public API — only the
framework integration modules in this package import from it.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from .._recorder import start_recording, stop_recording
from ..api import write_trace

TRACESNAP_ENV_GATE = "TRACESNAP_ENABLED"


def env_enabled() -> bool:
    """True when the `TRACESNAP_ENABLED=1` env var is set.

    Every `@traced` decorator gates on this so the wrapped view is a
    plain function call in production.
    """
    return os.environ.get(TRACESNAP_ENV_GATE) == "1"


def normalize_config(cfg: Any) -> tuple[Path, list[str], Any, str | None]:
    """Unpack a TRACESNAP config dict (or None) into a stable tuple.

    Returns (output_dir, source_files, redact_names, trace_id_prefix).
    """
    cfg = cfg or {}
    output_dir = Path(cfg.get("output_dir", "traces"))
    source_files = [str(p) for p in (cfg.get("source_files") or [])]
    redact_names = cfg.get("redact_names")
    trace_id_prefix = cfg.get("trace_id_prefix")
    return output_dir, source_files, redact_names, trace_id_prefix


def begin_recording(
    *,
    trace_name: str,
    source_files: list[str],
    redact_names: Any,
    trace_id_prefix: str | None = None,
) -> tuple[str, float]:
    """Start a recording session; return (trace_id, t0)."""
    prefix = trace_id_prefix or trace_name
    trace_id = f"{prefix}-{int(time.time() * 1000)}"
    start_recording(
        trace_id=trace_id,
        kind="request",
        source_files=source_files,
        redact_names=redact_names,
    )
    return trace_id, time.perf_counter()


def end_recording(
    *,
    trace_id: str,
    t0: float,
    output_dir: Path,
    entry: str,
    request_info: dict,
) -> None:
    """Stop recording and write the trace to disk."""
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    request_info = {**request_info, "duration_ms": duration_ms}
    try:
        trace = stop_recording(entry=entry, request=request_info)
    except RuntimeError:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    write_trace(trace, output_dir / f"{trace_id}.json")


def status_from_response(response: Any, default: int = 200) -> int:
    """Best-effort status from a returned response.

    Defaults to 200 on success: a path operation that returned without
    raising should be reported as 200 unless the response object disagrees
    (Django HttpResponse / Flask Response / Starlette Response all carry
    `status_code`; raw dicts / strings returned from FastAPI don't, and
    those serialize to 200).
    """
    return getattr(response, "status_code", default)


def status_from_exception(exc: BaseException, default: int = 500) -> int:
    # Framework exceptions (DRF APIException, Starlette HTTPException, Flask
    # HTTPException, etc.) all carry a `status_code` attribute.
    return getattr(exc, "status_code", default)
