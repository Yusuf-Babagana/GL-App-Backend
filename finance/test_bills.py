from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .btdataplug import BTDataPlugError
from .models import Transaction, Wallet

User = get_user_model()
P = 'finance.bills.BTDataPlugClient.'


class BillsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="bills@example.com", username="billsuser",
            password="password123", full_name="Bills User")
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.available_balance = Decimal('5000.00')
        self.wallet.save()
        token = RefreshToken.for_user(self.user).access_token
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def post(self, name, data):
        return self.client.post(reverse(name), data, content_type='application/json', **self.headers)

    def balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.available_balance

    @patch(P + 'purchase_airtime')
    def test_airtime_success(self, mock_buy):
        mock_buy.return_value = {'reference': 'BTD-1', 'status': 'successful'}
        r = self.post('airtime-purchase', {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 500})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.balance(), Decimal('4500.00'))
        self.assertEqual(Transaction.objects.get(wallet=self.wallet).status, Transaction.Status.SUCCESS)

    def test_airtime_rejects_bad_amount(self):
        r = self.post('airtime-purchase', {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 10})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.balance(), Decimal('5000.00'))

    @patch(P + 'purchase_airtime')
    def test_airtime_rejected_by_provider_charges_nothing(self, mock_buy):
        mock_buy.side_effect = BTDataPlugError('bad', code='purchase_failed', http_status=422)
        r = self.post('airtime-purchase', {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 500})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.balance(), Decimal('5000.00'))
        self.assertEqual(Transaction.objects.get(wallet=self.wallet).status, Transaction.Status.FAILED)

    @patch(P + 'purchase_airtime')
    def test_airtime_timeout_holds_funds_pending(self, mock_buy):
        mock_buy.side_effect = Exception('timeout')
        r = self.post('airtime-purchase', {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 500})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.balance(), Decimal('4500.00'))
        self.assertEqual(Transaction.objects.get(wallet=self.wallet).status, Transaction.Status.PENDING)

    @patch(P + 'purchase_electricity')
    @patch(P + 'get_discos')
    def test_electricity_charges_fee_and_returns_token(self, mock_discos, mock_buy):
        mock_discos.return_value = {'minimum_amount': '1000.00', 'service_fee': '100.00'}
        mock_buy.return_value = {'reference': 'BTD-2', 'status': 'successful', 'result': {'token': '1234-5678'}}
        r = self.post('electricity-purchase', {
            'disco': '01', 'meter_no': '12345678901', 'meter_type': 'prepaid',
            'phone': '08012345678', 'amount': 2000})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['token'], '1234-5678')
        self.assertEqual(self.balance(), Decimal('2900.00'))  # 2000 + 100 fee
        self.assertIn('1234-5678', Transaction.objects.get(wallet=self.wallet).description)

    @patch(P + 'get_discos')
    def test_electricity_below_minimum(self, mock_discos):
        mock_discos.return_value = {'minimum_amount': '1000.00', 'service_fee': '100.00'}
        r = self.post('electricity-purchase', {
            'disco': '01', 'meter_no': '12345678901', 'meter_type': 'prepaid',
            'phone': '08012345678', 'amount': 500})
        self.assertEqual(r.status_code, 400)

    @patch(P + 'purchase_cable')
    @patch(P + 'get_cable_plans')
    def test_cable_uses_provider_price_not_client_price(self, mock_plans, mock_buy):
        mock_plans.return_value = [{'package_id': 'gotv-jolli', 'cable_tv': 'gotv', 'name': 'Jolli', 'price': '3900.00'}]
        mock_buy.return_value = {'reference': 'BTD-3', 'status': 'pending'}
        r = self.post('cable-purchase', {
            'cable_tv': 'gotv', 'package_id': 'gotv-jolli', 'smartcard': '1234567890',
            'phone': '08012345678', 'amount': 1})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self.balance(), Decimal('1100.00'))
        self.assertEqual(Transaction.objects.get(wallet=self.wallet).status, Transaction.Status.PENDING)

    @patch(P + 'get_cable_plans')
    def test_cable_unknown_package(self, mock_plans):
        mock_plans.return_value = []
        r = self.post('cable-purchase', {
            'cable_tv': 'gotv', 'package_id': 'nope', 'smartcard': '1234567890', 'phone': '08012345678'})
        self.assertEqual(r.status_code, 400)

    @patch(P + 'purchase_airtime')
    def test_insufficient_wallet(self, mock_buy):
        r = self.post('airtime-purchase', {'service_id': 'mtn-airtime', 'phone': '08012345678', 'amount': 9000})
        self.assertEqual(r.status_code, 400)
        mock_buy.assert_not_called()
