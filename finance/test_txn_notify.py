from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .btdataplug import BTDataPlugError
from .models import Transaction, Wallet
from .reconcile import settle_from_order

User = get_user_model()
P = 'finance.bills.BTDataPlugClient.'
NOTIFY = 'finance.txn_notify.notify_user'


class TransactionNotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="n@example.com", username="notifyuser", password="password123", full_name="N User")
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.available_balance = Decimal('5000.00')
        self.wallet.save()
        token = RefreshToken.for_user(self.user).access_token
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def buy_airtime(self):
        return self.client.post(
            reverse('airtime-purchase'),
            {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 500},
            content_type='application/json', **self.headers)

    def run_and_collect(self, fn):
        with patch(NOTIFY) as notify, self.captureOnCommitCallbacks(execute=True):
            fn()
        return notify.call_args_list

    @patch(P + 'purchase_airtime')
    def test_success_notifies_once_with_details(self, buy):
        buy.return_value = {'reference': 'B1', 'status': 'successful'}
        calls = self.run_and_collect(self.buy_airtime)
        self.assertEqual(len(calls), 1)
        user, title, body, data = calls[0].args
        self.assertEqual(user, self.user)
        self.assertEqual(title, "Airtime purchase successful")
        self.assertIn("500.00", body)
        self.assertEqual(data['category'], 'airtime')
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['amount'], '500.00')
        self.assertTrue(data['timestamp'] and data['notification_id'])

    @patch(P + 'purchase_airtime')
    def test_pending_then_confirmed_then_duplicate_webhook(self, buy):
        buy.return_value = {'reference': 'B1', 'status': 'pending'}
        calls = self.run_and_collect(self.buy_airtime)
        self.assertEqual([c.args[3]['status'] for c in calls], ['pending'])
        self.assertIn('processing', calls[0].args[1])

        ref = Transaction.objects.get(wallet=self.wallet).reference
        order = {'client_reference': ref, 'status': 'successful'}
        calls = self.run_and_collect(lambda: settle_from_order(order))
        self.assertEqual([c.args[3]['status'] for c in calls], ['success'])
        # The provider re-delivers the webhook: no second notification.
        self.assertEqual(self.run_and_collect(lambda: settle_from_order(order)), [])

    @patch(P + 'purchase_airtime')
    def test_failed_after_pending_is_refunded(self, buy):
        buy.return_value = {'reference': 'B1', 'status': 'pending'}
        self.buy_airtime()
        ref = Transaction.objects.get(wallet=self.wallet).reference
        calls = self.run_and_collect(
            lambda: settle_from_order({'client_reference': ref, 'status': 'failed', 'failure_reason': 'x'}))
        self.assertEqual(len(calls), 1)
        _, title, body, data = calls[0].args
        self.assertEqual(title, "Airtime purchase failed")
        self.assertIn("refunded", body)
        self.assertEqual(data['status'], 'failed')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('5000.00'))

    @patch(P + 'purchase_airtime')
    def test_reversal_of_successful_order(self, buy):
        buy.return_value = {'reference': 'B1', 'status': 'successful'}
        self.buy_airtime()
        ref = Transaction.objects.get(wallet=self.wallet).reference
        calls = self.run_and_collect(
            lambda: settle_from_order({'client_reference': ref, 'status': 'reversed'}))
        self.assertEqual(len(calls), 1)
        self.assertIn("reversed", calls[0].args[2])

    @patch(P + 'purchase_airtime')
    def test_provider_rejection_says_not_charged(self, buy):
        buy.side_effect = BTDataPlugError('bad', code='purchase_failed', http_status=422)
        calls = self.run_and_collect(self.buy_airtime)
        self.assertEqual(len(calls), 1)
        _, title, body, data = calls[0].args
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['amount'], '500.00')
        self.assertIn("not charged", body)

    def test_insufficient_balance_sends_nothing(self):
        self.wallet.available_balance = Decimal('1.00')
        self.wallet.save()
        self.assertEqual(self.run_and_collect(self.buy_airtime), [])

    @patch(P + 'purchase_airtime')
    def test_notification_failure_never_breaks_purchase(self, buy):
        buy.return_value = {'reference': 'B1', 'status': 'successful'}
        with patch(NOTIFY, side_effect=RuntimeError("expo down")), \
                self.captureOnCommitCallbacks(execute=True):
            r = self.buy_airtime()
        self.assertEqual(r.status_code, 200)
