"""Runs real money scenarios against a throw-away test database and prints the ledger."""
import os
import sys
from datetime import timedelta
from decimal import Decimal
from io import StringIO

sys.path.insert(0, r"c:\Users\DELL\Desktop\DESKTOP\GL-Backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "globalink_core.settings")

import django
django.setup()
from django.conf import settings
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
settings.ALLOWED_HOSTS = ["*"]

from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0)
old = runner.setup_databases()

import logging
logging.disable(logging.CRITICAL)

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from finance.health import build_health_report
from finance.models import PlatformRevenue, Transaction, Wallet
from market.models import Dispute, Order, Product, Shop

User = get_user_model()


def client(u):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")
    return c


def world(tag):
    b = User.objects.create_user(email=f"buyer_{tag}@demo.test", password="x", full_name="Buyer")
    b.set_transaction_pin("1234"); b.save()
    s = User.objects.create_user(email=f"seller_{tag}@demo.test", password="x", full_name="Seller")
    a = User.objects.create_user(email=f"admin_{tag}@demo.test", password="x", full_name="Admin", is_staff=True)
    shop = Shop.objects.create(owner=s, name=f"Shop {tag}", is_active=True)
    p = Product.objects.create(shop=shop, name="Phone case", description="x", price=Decimal("10000.00"), stock=5)
    w, _ = Wallet.objects.get_or_create(user=b); w.available_balance = Decimal("25000.00"); w.save()
    return b, s, a, p


def pay(bc, p, key):
    r = bc.post("/api/market/checkout/", {
        "items": [{"product_id": p.id, "quantity": 1}], "payment_method": "wallet",
        "shipping_address": {"address": "1 Test Rd", "city": "Kano", "phone": "0800"}, "pin": "1234",
    }, format="json", HTTP_IDEMPOTENCY_KEY=key)
    return r


def balances(label, b, s):
    bw, sw = Wallet.objects.get(user=b), Wallet.objects.get(user=s)
    print(f"   {label:<38} buyer avail={bw.available_balance:>10}   seller avail={sw.available_balance:>9} locked={sw.locked_balance:>9}   platform={PlatformRevenue.get_singleton().total_commission}")


def ledger(order):
    print(f"   LEDGER for order #{order.id}:")
    for t in Transaction.objects.filter(related_order_id__contains=str(order.id)).order_by("created_at"):
        who = t.wallet.user.email.split("_")[0]
        print(f"     {t.created_at:%H:%M:%S}  {who:<7} {t.transaction_type:<15} {t.amount:>10}  {t.status:<8} {t.description[:70]}")


print("=" * 110)
print("SCENARIO 1 — happy path: pay -> held in escrow -> seller dispatches -> buyer confirms")
b, s, a, p = world("s1"); bc, sc = client(b), client(s)
balances("start", b, s)
o = Order.objects.get(pk=pay(bc, p, "s1").data["order"]["id"])
balances("after payment (money is LOCKED)", b, s)
sc.post(f"/api/market/seller/orders/{o.id}/dispatch/")
balances("after seller dispatches (still locked)", b, s)
r = bc.post(f"/api/market/buyer/orders/{o.id}/confirm/")
balances(f"after buyer CONFIRMS (HTTP {r.status_code})", b, s)
ledger(o)

print("\nSCENARIO 2 — network drops during payment: the app retries with the same Idempotency-Key")
b, s, a, p = world("s2"); bc = client(b)
r1 = pay(bc, p, "retry-me"); r2 = pay(bc, p, "retry-me"); r3 = pay(bc, p, "retry-me")
print(f"   attempt 1: HTTP {r1.status_code}   attempt 2 (retry): HTTP {r2.status_code} duplicate={r2.data.get('duplicate')}   attempt 3 (retry): HTTP {r3.status_code} duplicate={r3.data.get('duplicate')}")
print(f"   orders created: {Order.objects.filter(buyer=b).count()}   buyer charged: {Decimal('25000.00') - Wallet.objects.get(user=b).available_balance} (one item costs 10000.00)")

print("\nSCENARIO 3 — seller never delivers: buyer opens a dispute, admin refunds")
b, s, a, p = world("s3"); bc, sc, ac = client(b), client(s), client(a)
o = Order.objects.get(pk=pay(bc, p, "s3").data["order"]["id"])
sc.post(f"/api/market/seller/orders/{o.id}/dispatch/")
r = bc.post(f"/api/market/buyer/orders/{o.id}/dispute/", {"reason": "not_received", "description": "Seller marked it shipped 5 days ago, nothing arrived."}, format="json")
print(f"   buyer opens dispute: HTTP {r.status_code} -> {r.data['message']}")
o.refresh_from_db(); print(f"   order payment_status = {o.payment_status}")
print(f"   buyer tries to confirm while disputed:  HTTP {bc.post(f'/api/market/buyer/orders/{o.id}/confirm/').status_code}")
Order.objects.filter(pk=o.pk).update(dispatched_at=timezone.now() - timedelta(days=30))
call_command("process_escrow", stdout=StringIO())
balances("30 days later, auto-release job ran (frozen)", b, s)
sc.post(f"/api/market/seller/orders/{o.id}/dispute/respond/", {"response": "Handed to courier, ref 8841."}, format="json")
d = Dispute.objects.get(order=o)
print(f"   non-admin tries to resolve: HTTP {bc.post(f'/api/market/admin/disputes/{d.id}/resolve/', {'decision':'refund','note':'give me money'}, format='json').status_code}")
r = ac.post(f"/api/market/admin/disputes/{d.id}/resolve/", {"decision": "refund", "note": "No proof of delivery."}, format="json")
print(f"   admin resolves REFUND: HTTP {r.status_code}")
balances("after admin refund", b, s)
print(f"   admin resolves AGAIN: HTTP {ac.post(f'/api/market/admin/disputes/{d.id}/resolve/', {'decision':'release','note':'double click'}, format='json').status_code} (rejected, no second movement)")
balances("after the rejected second attempt", b, s)
ledger(o)

print("\nSCENARIO 4 — seller never ships and buyer forgets: auto-refund after 14 days")
b, s, a, p = world("s4"); bc = client(b)
o = Order.objects.get(pk=pay(bc, p, "s4").data["order"]["id"])
balances("paid, not shipped", b, s)
Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=15))
out = StringIO(); call_command("process_escrow", stdout=out); print("   process_escrow:", out.getvalue().strip().splitlines()[0])
balances("after process_escrow", b, s)

print("\nSCENARIO 5 — monitoring catches corrupted money")
b, s, a, p = world("s5"); bc = client(b)
pay(bc, p, "s5")
rep = build_health_report(check_provider=False)
print(f"   normal state:  healthy={rep['healthy']}  alerts={rep['alerts']}")
Wallet.objects.filter(user=s).update(locked_balance=Decimal("99999.00"))
rep = build_health_report(check_provider=False)
print(f"   after tampering with a seller's locked balance: healthy={rep['healthy']}")
for al in rep["alerts"]:
    print("     ALERT:", al)

runner.teardown_databases(old)
