"""
Deposits, withdrawals, notifications and the dashboard disputes tab.
Run with:  python manage.py test finance.test_money -v 2
"""
import hashlib
import hmac
import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from market.models import Dispute, Order, Product, Shop
from .models import Transaction, Wallet, WithdrawalTicket

User = get_user_model()
FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], NOTIFY_ASYNC=False)


def api(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


@FAST
class WithdrawalTests(TestCase):
    BANK = {"bank_code": "058", "bank_name": "GTBank", "account_number": "0123456789", "account_name": "W User"}

    def setUp(self):
        self.user = User.objects.create_user(email="w@x.com", password="pw12345!", full_name="W User")
        self.user.set_transaction_pin("4321")
        self.user.save()
        self.admin = User.objects.create_user(email="adm@x.com", password="pw12345!", full_name="Adm", is_staff=True)
        w, _ = Wallet.objects.get_or_create(user=self.user)
        w.available_balance = Decimal("5000.00")
        w.save()
        self.c, self.a = api(self.user), api(self.admin)

    def bal(self):
        return Wallet.objects.get(user=self.user).available_balance

    def ask(self, amount="2000.00", pin="4321", **extra):
        return self.c.post("/api/finance/withdraw/", {"amount": amount, "pin": pin, **self.BANK, **extra}, format="json")

    def test_request_holds_the_money_immediately(self):
        r = self.ask()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.bal(), Decimal("3000.00"))
        hold = Transaction.objects.get(reference=f"WDR-{r.data['ticket_id']}")
        self.assertEqual((hold.amount, hold.status), (Decimal("-2000.00"), "pending"))

    def test_held_money_cannot_be_spent_or_withdrawn_again(self):
        self.ask("4000.00")
        self.assertEqual(self.ask("2000.00").status_code, 400)       # only 1000 left
        self.assertEqual(self.bal(), Decimal("1000.00"))
        self.assertEqual(WithdrawalTicket.objects.count(), 1)

    def test_pin_is_required_and_checked(self):
        self.assertEqual(self.ask(pin="").status_code, 400)
        self.assertEqual(self.ask(pin="0000").status_code, 400)
        self.assertEqual(self.bal(), Decimal("5000.00"))
        self.user.transaction_pin = ""
        self.user.save()
        self.assertEqual(self.ask().status_code, 400)

    def test_rejects_bad_amounts(self):
        for bad in ("0", "-50", "NaN", "Infinity", "abc", "1000.555", "50"):
            self.assertEqual(self.ask(bad).status_code, 400, bad)
        self.assertEqual(self.bal(), Decimal("5000.00"))
        self.assertEqual(WithdrawalTicket.objects.count(), 0)

    def test_frozen_wallet_cannot_withdraw(self):
        Wallet.objects.filter(user=self.user).update(is_frozen=True)
        self.assertEqual(self.ask().status_code, 400)
        self.assertEqual(self.bal(), Decimal("5000.00"))

    def test_approve_marks_paid_without_touching_balance_again_and_only_once(self):
        tid = self.ask().data["ticket_id"]
        r = self.a.post(f"/api/finance/admin/withdrawals/{tid}/confirm/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.bal(), Decimal("3000.00"))             # not deducted a second time
        self.assertEqual(Transaction.objects.get(reference=f"WDR-{tid}").status, "success")
        again = self.a.post(f"/api/finance/admin/withdrawals/{tid}/confirm/")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.bal(), Decimal("3000.00"))

    def test_reject_returns_the_money_exactly_once(self):
        tid = self.ask().data["ticket_id"]
        staff = Client()
        staff.force_login(self.admin)
        r1 = staff.post(f"/api/finance/withdraw/{tid}/update-status/", {"action": "reject"})
        self.assertEqual(r1.content, b"rejected")
        self.assertEqual(self.bal(), Decimal("5000.00"))
        r2 = staff.post(f"/api/finance/withdraw/{tid}/update-status/", {"action": "reject"})
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(self.bal(), Decimal("5000.00"))
        self.assertEqual(staff.post(f"/api/finance/withdraw/{tid}/update-status/", {"action": "approve"}).status_code, 400)
        self.assertEqual(Transaction.objects.get(reference=f"WDR-{tid}").status, "failed")
        self.assertEqual(Transaction.objects.get(reference=f"WDR-{tid}-REFUND").amount, Decimal("2000.00"))

    def test_dashboard_approve_and_api_approve_cannot_both_pay(self):
        tid = self.ask().data["ticket_id"]
        staff = Client()
        staff.force_login(self.admin)
        self.assertEqual(staff.post(f"/api/finance/withdraw/{tid}/update-status/", {"action": "approve"}).content, b"approved")
        self.assertEqual(self.a.post(f"/api/finance/admin/withdrawals/{tid}/confirm/").status_code, 400)
        self.assertEqual(self.bal(), Decimal("3000.00"))

    def test_old_ticket_that_held_nothing_deducts_on_approve_and_refunds_nothing_on_reject(self):
        approve_me = WithdrawalTicket.objects.create(user=self.user, amount=Decimal("1000.00"), **self.BANK)
        reject_me = WithdrawalTicket.objects.create(user=self.user, amount=Decimal("1000.00"), **self.BANK)
        self.assertEqual(self.a.post(f"/api/finance/admin/withdrawals/{approve_me.pk}/confirm/").status_code, 200)
        self.assertEqual(self.bal(), Decimal("4000.00"))             # taken now, as before
        staff = Client()
        staff.force_login(self.admin)
        staff.post(f"/api/finance/withdraw/{reject_me.pk}/update-status/", {"action": "reject"})
        self.assertEqual(self.bal(), Decimal("4000.00"))             # no free money from rejecting

    def test_user_is_told_when_paid(self):
        tid = self.ask().data["ticket_id"]
        self.a.post(f"/api/finance/admin/withdrawals/{tid}/confirm/")
        self.assertTrue(any("Withdrawal paid" in m.subject and m.to == ["w@x.com"] for m in mail.outbox))


@FAST
class MonnifyWebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="m@x.com", password="pw12345!", full_name="M")
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.c = APIClient()

    def send(self, payload, sign=True):
        body = json.dumps(payload).encode()
        sig = hmac.new(settings.MONNIFY_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest() if sign else "bad"
        return self.c.post("/api/finance/monnify-webhook/", data=body, content_type="application/json",
                           HTTP_MONNIFY_SIGNATURE=sig)

    def deposit(self, ref="MNFY|1", amount="5000.00"):
        return {"eventType": "SUCCESSFUL_TRANSACTION", "eventData": {
            "paymentReference": ref, "amountPaid": amount, "settlementAmount": amount,
            "product": {"reference": str(self.wallet.account_reference)}}}

    def bal(self):
        self.wallet.refresh_from_db()
        return self.wallet.available_balance

    def test_unsigned_or_badly_signed_webhooks_do_nothing(self):
        self.assertEqual(self.send(self.deposit(), sign=False).status_code, 401)
        self.assertEqual(self.bal(), Decimal("0"))

    def test_deposit_credits_once_net_of_fee_and_replays_are_acknowledged(self):
        r1 = self.send(self.deposit())
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(self.bal(), Decimal("4950.00"))             # 1% processing fee on 5000
        for _ in range(3):                                           # Monnify retries
            self.assertEqual(self.send(self.deposit()).status_code, 200)
        self.assertEqual(self.bal(), Decimal("4950.00"))
        self.assertEqual(Transaction.objects.filter(reference="MNFY|1").count(), 1)

    def test_zero_or_missing_amount_is_refused(self):
        self.assertEqual(self.send(self.deposit(ref="MNFY|z", amount="0")).status_code, 400)
        self.assertEqual(self.bal(), Decimal("0"))

    def test_payment_matching_an_order_never_changes_the_order(self):
        seller = User.objects.create_user(email="s@x.com", password="pw12345!", full_name="S")
        shop = Shop.objects.create(owner=seller, name="S", is_active=True)
        order = Order.objects.create(buyer=self.user, shop=shop, total_price=Decimal("1000"),
                                     payment_status=Order.PaymentStatus.CONFIRMED,
                                     delivery_status=Order.DeliveryStatus.DELIVERED, monnify_reference="ORD-REF-1")
        r = self.send({"eventType": "SUCCESSFUL_TRANSACTION", "eventData": {
            "paymentReference": "ORD-REF-1", "amountPaid": "1000", "settlementAmount": "1000", "product": {}}})
        self.assertEqual(r.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.CONFIRMED)   # not flipped back to PAID
        self.assertEqual(self.bal(), Decimal("0"))

    def test_disbursement_event_without_reference_cannot_refund_a_random_transaction(self):
        self.wallet.available_balance = Decimal("100")
        self.wallet.save()
        Transaction.objects.create(wallet=self.wallet, amount=Decimal("-5000"), transaction_type="withdrawal",
                                   status="success", reference=None, description="unrelated old withdrawal")
        r = self.send({"eventType": "DISBURSEMENT_FAILED", "eventData": {}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.bal(), Decimal("100"))                 # nothing was refunded


@FAST
class RetiredAndInputTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="r@x.com", password="pw12345!", full_name="R")
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_old_nellobyte_deposit_endpoint_is_closed_and_credits_nothing(self):
        for method in ("get", "post"):
            r = getattr(Client(), method)("/api/finance/webhook/deposit/?orderid=123&orderremark=(r)")
            self.assertEqual(r.status_code, 410)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal("0"))


@FAST
class DisputeNotificationAndDashboardTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(email="buyer@x.com", password="pw12345!", full_name="B")
        self.seller = User.objects.create_user(email="seller@x.com", password="pw12345!", full_name="S")
        self.admin = User.objects.create_user(email="boss@x.com", password="pw12345!", full_name="Boss", is_staff=True)
        self.buyer.set_transaction_pin("1234")
        self.buyer.save()
        shop = Shop.objects.create(owner=self.seller, name="Shop", is_active=True)
        self.product = Product.objects.create(shop=shop, name="W", description="x", price=Decimal("1000"), stock=5)
        w, _ = Wallet.objects.get_or_create(user=self.buyer)
        w.available_balance = Decimal("2000")
        w.save()
        self.b, self.s, self.a = api(self.buyer), api(self.seller), api(self.admin)
        self.b.post("/api/market/checkout/", {
            "items": [{"product_id": self.product.id, "quantity": 1}], "payment_method": "wallet",
            "shipping_address": {"address": "1", "city": "K", "phone": "0"}, "pin": "1234"},
            format="json", HTTP_IDEMPOTENCY_KEY="n1")
        self.order = Order.objects.get(buyer=self.buyer)
        self.s.post(f"/api/market/seller/orders/{self.order.id}/dispatch/")
        mail.outbox.clear()

    def to(self):
        return sorted(addr for m in mail.outbox for addr in m.to)

    @override_settings(ADMINS=[("Ops", "ops@x.com")])
    def test_everyone_involved_is_told_at_each_step(self):
        self.b.post(f"/api/market/buyer/orders/{self.order.id}/dispute/",
                    {"reason": "not_received", "description": "nothing ever arrived here"}, format="json")
        self.assertEqual(self.to(), ["buyer@x.com", "ops@x.com", "seller@x.com"])
        mail.outbox.clear()

        self.s.post(f"/api/market/seller/orders/{self.order.id}/dispute/respond/",
                    {"response": "Courier tracking 9911"}, format="json")
        self.assertEqual(self.to(), ["buyer@x.com"])
        mail.outbox.clear()

        d = Dispute.objects.get(order=self.order)
        self.a.post(f"/api/market/admin/disputes/{d.id}/resolve/", {"decision": "refund", "note": "No proof"}, format="json")
        self.assertEqual(self.to(), ["buyer@x.com", "seller@x.com"])
        self.assertTrue(all("Dispute resolved" in m.subject for m in mail.outbox))

    def test_seller_told_when_buyer_confirms(self):
        self.b.post(f"/api/market/buyer/orders/{self.order.id}/confirm/")
        self.assertEqual(self.to(), ["seller@x.com"])

    def test_a_notification_failure_never_breaks_the_payment(self):
        from unittest.mock import patch
        with patch("globalink_core.notify.send_mail", side_effect=RuntimeError("smtp down")):
            r = self.b.post(f"/api/market/buyer/orders/{self.order.id}/confirm/")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_lists_open_disputes_and_staff_can_decide_from_it(self):
        self.b.post(f"/api/market/buyer/orders/{self.order.id}/dispute/",
                    {"reason": "damaged", "description": "screen cracked on arrival"}, format="json")
        d = Dispute.objects.get(order=self.order)
        staff = Client()
        staff.force_login(self.admin)
        page = staff.get("/")
        self.assertContains(page, 'id="tab-disputes"')
        self.assertContains(page, "screen cracked on arrival")
        self.assertContains(page, "buyer@x.com")

        no_note = staff.post(f"/api/admin/disputes/{d.id}/resolve/", {"decision": "refund", "note": ""})
        self.assertEqual(no_note.status_code, 400)
        ok = staff.post(f"/api/admin/disputes/{d.id}/resolve/", {"decision": "refund", "note": "Photos confirm damage"})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(Wallet.objects.get(user=self.buyer).available_balance, Decimal("2000"))
        again = staff.post(f"/api/admin/disputes/{d.id}/resolve/", {"decision": "release", "note": "second click"})
        self.assertEqual(again.status_code, 400)

    def test_dashboard_disputes_are_staff_only(self):
        normal = Client()
        normal.force_login(self.buyer)
        d_url = "/api/admin/disputes/1/resolve/"
        self.assertIn(normal.post(d_url, {"decision": "refund", "note": "give me money"}).status_code, (302, 403))
        self.assertEqual(Wallet.objects.get(user=self.buyer).available_balance, Decimal("1000"))
