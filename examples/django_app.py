"""
Single-file Django example. Run with:

    pip install -e .[django]
    TRACESNAP_ENABLED=1 python examples/django_app.py runserver 5052

Hit:
    curl http://127.0.0.1:5052/checkout

Traces land in ./traces/<id>.json. Open one with:
    tracesnap view traces/<id>.json

Recording is opt-in per view via @traced. Without TRACESNAP_ENABLED=1
the decorator is a no-op.
"""
import os
import sys

import django
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django.core.management import execute_from_command_line


HERE = os.path.abspath(__file__)

settings.configure(
    DEBUG=False,
    SECRET_KEY="example-key-not-for-prod",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["*"],
    MIDDLEWARE=[],
    TRACESNAP={
        "output_dir": "traces",
        "source_files": [HERE],
    },
    INSTALLED_APPS=[],
)
django.setup()


from tracesnap.integrations.django import traced  # noqa: E402  (after django.setup)


def validate_cart(items):
    if not items:
        raise ValueError("empty cart")
    cleaned = []
    for x in items:
        cleaned.append(float(x))
    return cleaned


def compute_total(items, coupon_pct):
    subtotal = 0.0
    for amount in items:
        subtotal += amount
    if coupon_pct > 0:
        return subtotal * (1.0 - coupon_pct / 100.0)
    return subtotal


@traced
def checkout(request):
    import requests
    raw = [100, 50, 25]
    cart = validate_cart(raw)
    r = requests.get("https://httpbin.org/get", params={"q": "trace-demo"}, timeout=10)
    coupon = 10 if r.status_code == 200 else 0
    total = compute_total(cart, coupon)
    return JsonResponse({"items": cart, "coupon_pct": coupon, "total": total})


urlpatterns = [path("checkout", checkout)]


if __name__ == "__main__":
    execute_from_command_line(sys.argv)
