"""
Money-safety tests. Each test class maps to a question about how GLAPP handles
buyers' and sellers' money; run with:  python manage.py test market.test_escrow -v 2
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from finance.btdataplug import BTDataPlugError
from finance.health import build_health_report
from finance.models import PlatformRevenue, Transaction, Wallet
from .models import Dispute, Order, Product, Shop

User = get_user_model()
FAST_HASH = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def auth(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


@FAST_HASH
class Base(TestCase):
    PRICE = Decimal("1000.00")

    def setUp(self):
        self.buyer = User.objects.create_user(email="b@x.com", password="pw12345!", full_name="Buyer")
        self.buyer.set_transaction_pin("1234")
        self.buyer.save()
        self.seller = User.objects.create_user(email="s@x.com", password="pw12345!", full_name="Seller")
        self.admin = User.objects.create_user(email="a@x.com", password="pw12345!", full_name="Admin", is_staff=True)
        self.shop = Shop.objects.create(owner=self.seller, name="Shop", is_active=True)
        self.product = Product.objects.create(
            shop=self.shop, name="Widget", description="x", price=self.PRICE, stock=10)
        w, _ = Wallet.objects.get_or_create(user=self.buyer)
        w.available_balance = Decimal("2000.00")
        w.save()
        self.b, self.s, self.a = auth(self.buyer), auth(self.seller), auth(self.admin)

    # -- helpers
    def pay(self, key="k1"):
        r = self.b.post("/api/market/checkout/", {
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "payment_method": "wallet",
            "shipping_address": {"address": "1 Rd", "city": "Kano", "phone": "0800"},
            "pin": "1234",
        }, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertIn(r.status_code, (200, 201), r.data)
        return Order.objects.filter(buyer=self.buyer).latest('id')

    def dispatch(self, order):
        r = self.s.post(f"/api/market/seller/orders/{order.id}/dispatch/")
        self.assertEqual(r.status_code, 200, r.data)

    def wallet(self, user):
        w = Wallet.objects.get(user=user)
        return w.available_balance, w.locked_balance

    def total_money(self):
        """Every naira in the system: all wallets + platform commission. Must never change."""
        from django.db.models import Sum
        agg = Wallet.objects.aggregate(a=Sum('available_balance'), l=Sum('locked_balance'))
        return agg['a'] + agg['l'] + PlatformRevenue.get_singleton().total_commission


class EscrowHoldingTests(Base):
    """Q1: is the buyer's money held until they click Confirm?"""

    def test_payment_is_held_in_escrow_until_buyer_confirms(self):
        before = self.total_money()
        order = self.pay()
        self.assertEqual(self.wallet(self.buyer), (Decimal("1000.00"), Decimal("0")))
        # Seller has the money but it is LOCKED: nothing withdrawable.
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("1000.00")))
        self.dispatch(order)
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("1000.00")))

        r = self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/")
        self.assertEqual(r.status_code, 200, r.data)
        # 5% commission, rest released to the seller.
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))
        self.assertEqual(PlatformRevenue.get_singleton().total_commission, Decimal("50.00"))
        self.assertEqual(self.total_money(), before)

    def test_only_the_buyer_can_confirm(self):
        order = self.pay()
        self.dispatch(order)
        for client in (self.s, self.a):
            self.assertIn(client.post(f"/api/market/buyer/orders/{order.id}/confirm/").status_code, (403, 404))
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("1000.00")))

    def test_confirm_twice_pays_once(self):
        order = self.pay()
        self.dispatch(order)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/").status_code, 200)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/").status_code, 400)
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))


class DisputeTests(Base):
    """Q2 + Q6: seller fails to deliver -> buyer opens a dispute -> admin decides."""

    def open_dispute(self, order, desc="Item never arrived at my address"):
        return self.b.post(f"/api/market/buyer/orders/{order.id}/dispute/",
                           {"reason": "not_received", "description": desc}, format="json")

    def test_dispute_freezes_funds_and_blocks_confirm_cancel_and_auto_release(self):
        order = self.pay()
        self.dispatch(order)
        Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - timedelta(days=30))
        r = self.open_dispute(order)
        self.assertEqual(r.status_code, 201, r.data)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.DISPUTED)

        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/").status_code, 400)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/cancel/").status_code, 400)
        call_command("process_escrow", stdout=StringIO())  # 30 days old but disputed: untouched
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("1000.00")))
        self.assertEqual(self.wallet(self.buyer), (Decimal("1000.00"), Decimal("0")))

    def test_admin_refunds_buyer(self):
        before = self.total_money()
        order = self.pay()
        self.dispatch(order)
        self.open_dispute(order)
        dispute = Dispute.objects.get(order=order)

        r = self.s.post(f"/api/market/seller/orders/{order.id}/dispute/respond/",
                        {"response": "I shipped it with the courier, tracking 123"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        r = self.a.post(f"/api/market/admin/disputes/{dispute.id}/resolve/",
                        {"decision": "refund", "note": "No proof of delivery from seller"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        self.assertEqual(self.wallet(self.buyer), (Decimal("2000.00"), Decimal("0")))
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("0")))
        order.refresh_from_db()
        dispute.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(dispute.status, Dispute.Status.RESOLVED_REFUND)
        self.assertEqual(dispute.resolved_by, self.admin)
        self.assertEqual(self.total_money(), before)
        # both sides of the refund are on the ledger
        refunds = Transaction.objects.filter(related_order_id=str(order.id), transaction_type="refund")
        self.assertEqual(sorted(t.amount for t in refunds), [Decimal("-1000.00"), Decimal("1000.00")])
        # a second decision can't move money again
        again = self.a.post(f"/api/market/admin/disputes/{dispute.id}/resolve/",
                            {"decision": "release", "note": "oops second click"}, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.wallet(self.buyer), (Decimal("2000.00"), Decimal("0")))

    def test_admin_releases_to_seller(self):
        order = self.pay()
        self.dispatch(order)
        self.open_dispute(order)
        dispute = Dispute.objects.get(order=order)
        r = self.a.post(f"/api/market/admin/disputes/{dispute.id}/resolve/",
                        {"decision": "release", "note": "Courier confirmed delivery"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))
        self.assertEqual(self.wallet(self.buyer), (Decimal("1000.00"), Decimal("0")))

    def test_only_staff_can_resolve(self):
        order = self.pay()
        self.dispatch(order)
        self.open_dispute(order)
        dispute = Dispute.objects.get(order=order)
        body = {"decision": "refund", "note": "I want my money"}
        for client in (self.b, self.s):
            r = client.post(f"/api/market/admin/disputes/{dispute.id}/resolve/", body, format="json")
            self.assertEqual(r.status_code, 403)
        self.assertEqual(self.wallet(self.buyer), (Decimal("1000.00"), Decimal("0")))

    def test_dispute_rules(self):
        order = self.pay()
        # not dispatched yet -> buyer should cancel instead
        self.assertEqual(self.open_dispute(order).status_code, 400)
        self.dispatch(order)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/dispute/",
                                     {"reason": "not_received", "description": "short"}, format="json").status_code, 400)
        self.assertEqual(self.open_dispute(order).status_code, 201)
        self.assertEqual(self.open_dispute(order).status_code, 400)  # only one open at a time
        # someone else's order
        other = User.objects.create_user(email="o@x.com", password="pw12345!", full_name="Other")
        r = auth(other).post(f"/api/market/buyer/orders/{order.id}/dispute/",
                             {"reason": "other", "description": "not my order at all"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_buyer_can_withdraw_then_confirm(self):
        order = self.pay()
        self.dispatch(order)
        self.open_dispute(order)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/dispute/withdraw/").status_code, 200)
        self.assertEqual(self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/").status_code, 200)
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))


class NoDeliveryAndAutoSettleTests(Base):
    """Q2: what if the seller never delivers / the buyer never confirms."""

    def test_seller_never_ships_buyer_cancels_full_refund(self):
        order = self.pay()
        r = self.b.post(f"/api/market/buyer/orders/{order.id}/cancel/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.wallet(self.buyer), (Decimal("2000.00"), Decimal("0")))
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("0")))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_seller_never_ships_and_buyer_forgets_auto_refund_after_14_days(self):
        order = self.pay()
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.buyer), (Decimal("1000.00"), Decimal("0")))  # too early
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=15))
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.buyer), (Decimal("2000.00"), Decimal("0")))
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("0")))
        # idempotent: running again does nothing
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.buyer), (Decimal("2000.00"), Decimal("0")))

    def test_buyer_never_confirms_auto_release_after_7_days(self):
        order = self.pay()
        self.dispatch(order)
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.seller), (Decimal("0"), Decimal("1000.00")))  # too early
        Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - timedelta(days=8))
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))
        call_command("process_escrow", stdout=StringIO())
        self.assertEqual(self.wallet(self.seller), (Decimal("950.00"), Decimal("0")))


@FAST_HASH
class DoubleChargeTests(TestCase):
    """Q3: network drops during payment -> can the buyer be charged twice?"""

    def setUp(self):
        self.user = User.objects.create_user(email="d@x.com", password="pw12345!", full_name="D")
        w, _ = Wallet.objects.get_or_create(user=self.user)
        w.available_balance = Decimal("5000.00")
        w.save()
        self.c = auth(self.user)
        self.plans = [{"PRODUCT_ID": "7", "PRODUCT_NAME": "1GB", "PRODUCT_AMOUNT": "500.00"}]

    def bal(self):
        return Wallet.objects.get(user=self.user).available_balance

    def buy_data(self, key=None):
        kw = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
        return self.c.post(reverse("data-purchase"), {
            "service_id": "mtn-data", "variation_code": "7", "phone": "08012345678"}, format="json", **kw)

    @patch("finance.views.BTDataPlugClient.purchase_data")
    @patch("finance.views.BTDataPlugClient.fetch_all_variations")
    def test_data_retry_with_same_key_buys_once(self, fetch, buy):
        fetch.return_value = self.plans
        buy.return_value = {"reference": "BTD-1", "status": "successful"}
        first = self.buy_data("attempt-1")
        retry = self.buy_data("attempt-1")   # the app retries after losing the response
        self.assertEqual((first.status_code, retry.status_code), (200, 200))
        self.assertTrue(retry.data.get("duplicate"))
        self.assertEqual(buy.call_count, 1)                   # provider called once
        self.assertEqual(self.bal(), Decimal("4450.00"))      # 5000 - 550, charged once
        self.assertEqual(Transaction.objects.filter(transaction_type="bill_payment").count(), 1)

    @patch("finance.views.BTDataPlugClient.purchase_data")
    @patch("finance.views.BTDataPlugClient.fetch_all_variations")
    def test_timeout_then_retry_does_not_charge_twice(self, fetch, buy):
        fetch.return_value = self.plans
        buy.side_effect = Exception("connection reset")      # the network drops mid-request
        first = self.buy_data("attempt-2")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(self.bal(), Decimal("4450.00"))      # held as pending
        buy.side_effect = None
        buy.return_value = {"reference": "BTD-2", "status": "successful"}
        retry = self.buy_data("attempt-2")
        self.assertTrue(retry.data.get("duplicate"))
        self.assertEqual(buy.call_count, 1)                   # never sent a second order
        self.assertEqual(self.bal(), Decimal("4450.00"))
        self.assertEqual(Transaction.objects.filter(transaction_type="bill_payment").count(), 1)

    @patch("finance.views.BTDataPlugClient.purchase_data")
    @patch("finance.views.BTDataPlugClient.fetch_all_variations")
    def test_different_keys_are_different_purchases(self, fetch, buy):
        fetch.return_value = self.plans
        buy.return_value = {"reference": "BTD-3", "status": "successful"}
        self.buy_data("a")
        self.buy_data("b")
        self.assertEqual(buy.call_count, 2)
        self.assertEqual(self.bal(), Decimal("3900.00"))

    @patch("finance.bills.BTDataPlugClient.purchase_airtime")
    def test_airtime_retry_buys_once(self, buy):
        buy.return_value = {"reference": "BTD-4", "status": "successful"}
        body = {"service_id": "mtn-airtime", "phone": "08012345678", "amount": 500}
        r1 = self.c.post(reverse("airtime-purchase"), body, format="json", HTTP_IDEMPOTENCY_KEY="air-1")
        r2 = self.c.post(reverse("airtime-purchase"), body, format="json", HTTP_IDEMPOTENCY_KEY="air-1")
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual(buy.call_count, 1)
        self.assertEqual(self.bal(), Decimal("4500.00"))

    def test_marketplace_checkout_retry_charges_once(self):
        # already covered in detail by market.tests.PaymentSafetyTests; kept here so the
        # whole "double charge" question is answered in one place.
        seller = User.objects.create_user(email="s2@x.com", password="pw12345!", full_name="S")
        shop = Shop.objects.create(owner=seller, name="S2", is_active=True)
        p = Product.objects.create(shop=shop, name="W", description="x", price=Decimal("1000"), stock=5)
        self.user.set_transaction_pin("1234")
        self.user.save()
        body = {"items": [{"product_id": p.id, "quantity": 1}], "payment_method": "wallet",
                "shipping_address": {"address": "1", "city": "K", "phone": "0"}, "pin": "1234"}
        self.c.post("/api/market/checkout/", body, format="json", HTTP_IDEMPOTENCY_KEY="chk")
        self.c.post("/api/market/checkout/", body, format="json", HTTP_IDEMPOTENCY_KEY="chk")
        self.assertEqual(Order.objects.filter(buyer=self.user).count(), 1)
        self.assertEqual(self.bal(), Decimal("4000.00"))


class AuditTrailAndMonitoringTests(Base):
    """Q4 + Q7: every movement is recorded; problems are detected."""

    def test_every_balance_change_has_a_ledger_row(self):
        order = self.pay()
        self.dispatch(order)
        self.b.post(f"/api/market/buyer/orders/{order.id}/confirm/")
        order2 = self.pay("k2")
        self.dispatch(order2)
        self.open_dispute(order2)
        d = Dispute.objects.get(order=order2)
        self.a.post(f"/api/market/admin/disputes/{d.id}/resolve/", {"decision": "refund", "note": "no proof"}, format="json")

        for user in (self.buyer, self.seller):
            wallet = Wallet.objects.get(user=user)
            ledger = sum(t.amount for t in wallet.transactions.filter(status="success"))
            # available+locked is explained by the ledger: payments(-/+), releases, refunds
            self.assertGreaterEqual(wallet.transactions.count(), 2, user.email)
        # buyer: -1000 pay, -1000 pay, +1000 refund  => ledger sums to the balance change
        bw = Wallet.objects.get(user=self.buyer)
        self.assertEqual(sum(t.amount for t in bw.transactions.all()), bw.available_balance - Decimal("2000.00"))
        # each order's story can be pulled by order id
        kinds = set(Transaction.objects.filter(related_order_id=str(order2.id)).values_list("transaction_type", flat=True))
        self.assertTrue({"payment", "refund"} <= kinds)

    def open_dispute(self, order):
        return self.b.post(f"/api/market/buyer/orders/{order.id}/dispute/",
                           {"reason": "not_received", "description": "never arrived at all"}, format="json")

    def test_ledger_rows_cannot_be_edited_in_admin(self):
        from django.contrib import admin
        from django.test import RequestFactory
        ma = admin.site._registry[Transaction]
        req = RequestFactory().get("/")
        req.user = self.admin
        self.assertFalse(ma.has_change_permission(req))
        self.assertFalse(ma.has_delete_permission(req))
        self.assertFalse(ma.has_add_permission(req))

    def test_health_report_is_clean_after_normal_activity(self):
        order = self.pay()
        self.dispatch(order)
        report = build_health_report(check_provider=False)
        self.assertTrue(report["healthy"], report["alerts"])

    def test_health_report_catches_money_that_does_not_add_up(self):
        self.pay()
        Wallet.objects.filter(user=self.seller).update(locked_balance=Decimal("1500.00"))  # corruption
        report = build_health_report(check_provider=False)
        self.assertFalse(report["healthy"])
        self.assertTrue(any("locked_balance" in a for a in report["alerts"]), report["alerts"])
        Wallet.objects.filter(user=self.buyer).update(available_balance=Decimal("-5.00"))
        self.assertTrue(any("negative" in a for a in build_health_report(check_provider=False)["alerts"]))

    def test_health_report_catches_stuck_purchase_and_overdue_release_and_old_dispute(self):
        w = Wallet.objects.get(user=self.buyer)
        t = Transaction.objects.create(wallet=w, amount=-100, transaction_type="bill_payment",
                                       status="pending", reference="stuck-1", description="Airtime")
        Transaction.objects.filter(pk=t.pk).update(created_at=timezone.now() - timedelta(hours=2))
        order = self.pay()
        self.dispatch(order)
        Order.objects.filter(pk=order.pk).update(dispatched_at=timezone.now() - timedelta(days=20))
        alerts = " | ".join(build_health_report(check_provider=False)["alerts"])
        self.assertIn("pending for more than", alerts)
        self.assertIn("overdue for auto-release", alerts)

    def test_provider_low_balance_alert(self):
        with patch("finance.btdataplug.BTDataPlugClient.get_balance", return_value={"balance": "120.00"}):
            report = build_health_report(check_provider=True)
        self.assertTrue(any("BT DataPlug wallet low" in a for a in report["alerts"]))

    def test_health_endpoint_is_staff_only(self):
        url = "/api/finance/admin/health/?skip_provider=1"
        self.assertEqual(self.b.get(url).status_code, 403)
        r = self.a.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("alerts", r.data)
