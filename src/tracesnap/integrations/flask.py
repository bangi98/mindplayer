"""Flask integration: the `@traced` decorator.

Decorate any view function to record a tracesnap trace just for that
endpoint. Reads recording config from `current_app.config["TRACESNAP"]`;
recording is gated on the `TRACESNAP_ENABLED=1` environment variable, so
the decorator is a no-op otherwise.

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
"""
from __future__ import annotations

import functools

try:
    from flask import current_app, request
except ImportError as exc:  # pragma: no cover
    raise ImportError("Flask is not installed. Try: pip install tracesnap[flask]") from exc

from ._common import (
    begin_recording,
    end_recording,
    env_enabled,
    normalize_config,
    status_from_exception,
    status_from_response,
)


def traced(func=None, *, name: str | None = None):
    """Record a trace for the decorated Flask view. Usage:

        @traced
        def view(): ...

        @traced(name="checkout")
        def view(): ...

    Stack `@traced` *below* the route decorator:

        @app.route("/checkout")
        @traced
        def checkout(): ...
    """

    def decorate(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not env_enabled():
                return f(*args, **kwargs)

            try:
                cfg = current_app.config.get("TRACESNAP")
            except RuntimeError:
                # outside application context — skip
                return f(*args, **kwargs)

            output_dir, source_files, redact_names, prefix = normalize_config(cfg)
            if not source_files:
                return f(*args, **kwargs)

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
                    request_info={
                        "method": request.method,
                        "path": request.path,
                        "status": status_code,
                    },
                )

        return wrapper

    if func is None:
        return decorate
    return decorate(func)
