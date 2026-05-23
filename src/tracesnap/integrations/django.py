"""Django integration: the `@traced` decorator.

Decorate any view function (or DRF action method) to record a tracesnap
trace just for that endpoint. Reads recording config from
`settings.TRACESNAP`; recording is gated on the `TRACESNAP_ENABLED=1`
environment variable, so the decorator is a no-op otherwise.

    # settings.py
    TRACESNAP = {
        "output_dir": "traces",
        "source_files": [BASE_DIR / "myapp" / "views.py"],
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
"""
from __future__ import annotations

import functools

try:
    from django.conf import settings as _django_settings  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError("Django is not installed. Try: pip install tracesnap[django]") from exc

from ._common import (
    begin_recording,
    end_recording,
    env_enabled,
    normalize_config,
    status_from_exception,
    status_from_response,
)


def _find_request(args):
    """Locate the HttpRequest in positional args.

    Function-based views receive it as the first arg; ViewSet action
    methods receive it as the second (after `self`).
    """
    for a in args:
        if hasattr(a, "method") and hasattr(a, "path") and hasattr(a, "META"):
            return a
    return None


def traced(func=None, *, name: str | None = None):
    """Record a trace for the decorated view/action. Usage:

        @traced
        def view(request): ...

        @traced(name="checkout")
        def view(request): ...
    """

    def decorate(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not env_enabled():
                return f(*args, **kwargs)

            from django.conf import settings

            output_dir, source_files, redact_names, prefix = normalize_config(
                getattr(settings, "TRACESNAP", None)
            )
            if not source_files:
                return f(*args, **kwargs)

            request = _find_request(args)
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
                        "method": getattr(request, "method", "?"),
                        "path": getattr(request, "path", "?"),
                        "status": status_code,
                    },
                )

        return wrapper

    if func is None:
        return decorate
    return decorate(func)
