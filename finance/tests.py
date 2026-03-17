from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from decimal import Decimal
from unittest.mock import patch
from .models import Wallet, Transaction
from .nellobyte import NellobyteClient

User = get_user_model()

class DataPurchaseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            full_name="Test User"
        )
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.balance = Decimal('1000.00')
        self.wallet.save()
        self.client.login(email="test@example.com", password="password123")

    @patch('finance.views.NellobyteClient.purchase_data')
    def test_data_purchase_success(self, mock_purchase):
        # Mock successful Nellobyte response
        mock_purchase.return_value = {
            'statuscode': '100',
            'status': 'ORDER_RECEIVED',
            'orderid': '12345'
        }

        url = reverse('data-purchase')
        data = {
            'service_id': 'mtn-data',
            'variation_code': 'MTN500',
            'phone': '08012345678',
            'amount': '500.00'
        }

        response = self.client.post(url, data, content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('500.00'))
        
        # Verify transaction
        transaction = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(transaction.status, Transaction.Status.SUCCESS)
        self.assertEqual(transaction.amount, Decimal('-500.00'))

    @patch('finance.views.NellobyteClient.purchase_data')
    def test_data_purchase_api_failure_auto_refund(self, mock_purchase):
        # Mock failed Nellobyte response
        mock_purchase.return_value = {
            'statuscode': '201',
            'status': 'INVALID_DATA_PLAN'
        }

        url = reverse('data-purchase')
        data = {
            'service_id': 'mtn-data',
            'variation_code': 'INVALID',
            'phone': '08012345678',
            'amount': '200.00'
        }

        response = self.client.post(url, data, content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00')) # Refunded
        
        # Verify transaction status
        transaction = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(transaction.status, Transaction.Status.FAILED)
        self.assertIn("(Refunded: INVALID_DATA_PLAN)", transaction.description)

    @patch('finance.views.NellobyteClient.purchase_data')
    def test_data_purchase_critical_failure_pending(self, mock_purchase):
        # Mock network error
        mock_purchase.side_effect = Exception("Connection Timeout")

        url = reverse('data-purchase')
        data = {
            'service_id': 'mtn-data',
            'variation_code': 'MTN500',
            'phone': '08012345678',
            'amount': '500.00'
        }

        response = self.client.post(url, data, content_type='application/json')
        
        self.assertEqual(response.status_code, 202)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('500.00')) # Not refunded yet
        
        # Verify transaction status
        transaction = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(transaction.status, Transaction.Status.PENDING)

    @patch('finance.views.NellobyteClient.fetch_plans')
    def test_data_variations_success(self, mock_fetch):
        # Mock Nellobyte plans response
        mock_fetch.return_value = [
            {"ID": "1", "Name": "500MB", "Amount": "100.00"},
            {"ID": "2", "Name": "1GB", "Amount": "200.00"}
        ]

        url = reverse('data-plans')
        response = self.client.get(url, {'service_id': 'mtn-data'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['plans']), 2)
        self.assertEqual(response.json()['plans'][0]['variation_code'], "1")
