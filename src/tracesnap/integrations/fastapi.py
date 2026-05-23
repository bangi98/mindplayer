"""FastAPI / Starlette integration: the `@traced` decorator.

Decorate any path operation (sync or async) to record a tracesnap trace
just for that endpoint. FastAPI has no central settings object, so call
`configure(...)` once at startup to set the recording config. Recording
is gated on the `TRACESNAP_ENABLED=1` environment variable, so the
decorator is a no-op otherwise.

    from fastapi import FastAPI
    from tracesnap.integrations.fastapi import configure, traced

    app = FastAPI()
    configure(output_dir="traces", source_files=[__file__])

    @app.get("/checkout")
    @traced
    async def checkout():
        ...

Stack `@traced` *below* the route decorator (closer to the function) so
FastAPI's dependency-injection sees the wrapped signature.

To get request method/path in the trace, declare a `request: Request`
parameter on the view (FastAPI only injects it if asked). Without it the
trace is still produced; method/path just show as "?".

Note: `sys.settrace` is per-thread; contextvars are per-asyncio-task.
Single-handler-per-request is the supported case. Concurrent
`asyncio.gather(...)` of multiple sub-tasks within a traced handler
share the same recording session.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any

try:
    from fastapi import Request  # noqa: F401  — type imported for clarity
except ImportError as exc:  # pragma: no cover
    raise ImportError("FastAPI is not installed. Try: pip install tracesnap[fastapi]") from exc

from ._common import (
    begin_recording,
    end_recording,
    env_enabled,
    normalize_config,
    status_from_exception,
    status_from_response,
)

_config: dict[str, Any] = {}


def configure(
    *,
    output_dir: str = "traces",
    source_files: list[str] | None = None,
    redact_names: Any = None,
    trace_id_prefix: str | None = None,
) -> None:
    """Set the tracesnap recording config for this FastAPI app.

    Call once at startup, before requests start arriving. Replaces any
    previous configuration.
    """
    _config.clear()
    _config.update(
        {
            "output_dir": output_dir,
            "source_files": list(source_files or []),
            "redact_names": redact_names,
            "trace_id_prefix": trace_id_prefix,
        }
    )


def _find_request(args, kwargs):
    """Find a Starlette/FastAPI Request in the call args, if any."""
    for a in list(args) + list(kwargs.values()):
        if hasattr(a, "method") and hasattr(a, "url") and hasattr(a, "headers"):
            return a
    return None


def _request_info(request, status_code):
    if request is None:
        return {"method": "?", "path": "?", "status": status_code}
    return {
        "method": request.method,
        "path": str(getattr(request, "url", "?").path) if hasattr(request, "url") else "?",
        "status": status_code,
    }


def traced(func=None, *, name: str | None = None):
    """Record a trace for the decorated path operation. Usage:

        @traced
        async def view(): ...

        @traced(name="checkout")
        def view(): ...
    """

    def decorate(f):
        is_async = inspect.iscoroutinefunction(f)

        if is_async:

            @functools.wraps(f)
            async def async_wrapper(*args, **kwargs):
                if not env_enabled():
                    return await f(*args, **kwargs)

                output_dir, source_files, redact_names, prefix = normalize_config(_config)
                if not source_files:
                    return await f(*args, **kwargs)

                request = _find_request(args, kwargs)
                trace_name = name or f.__name__
                trace_id, t0 = begin_recording(
                    trace_name=trace_name,
                    source_files=source_files,
                    redact_names=redact_names,
                    trace_id_prefix=prefix,
                )
                status_code = 500
                try:
                    response = await f(*args, **kwargs)
                    status_code = status_from_response(response)
                    return response
                except Exception as exc:
                    status_code = status_from_exception(exc, status_code)
                    raise
                finally:
                    end_recording(
                        trace_id=trace_id,
                        t0=t0,
                        output_dir=output_dir,
                        entry=f.__qualname__,
                        request_info=_request_info(request, status_code),
                    )

            return async_wrapper

        @functools.wraps(f)
        def sync_wrapper(*args, **kwargs):
            if not env_enabled():
                return f(*args, **kwargs)

            output_dir, source_files, redact_names, prefix = normalize_config(_config)
            if not source_files:
                return f(*args, **kwargs)

            request = _find_request(args, kwargs)
            trace_name = name or f.__name__
            trace_id, t0 = begin_recording(
                trace_name=trace_name,
                source_files=source_files,
                redact_names=redact_names,
                trace_id_prefix=prefix,
            )
            status_code = 500
            try:
                response = f(*args, **kwargs)
                status_code = status_from_response(response)
                return response
            except Exception as exc:
                status_code = status_from_exception(exc, status_code)
                raise
            finally:
                end_recording(
                    trace_id=trace_id,
                    t0=t0,
                    output_dir=output_dir,
                    entry=f.__qualname__,
                    request_info=_request_info(request, status_code),
                )

        return sync_wrapper

    if func is None:
        return decorate
    return decorate(func)
