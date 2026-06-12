from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from decimal import Decimal
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import Wallet, Transaction
from .nellobyte import NellobyteClient
from .utils import MonnifyAPI

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
        self.wallet.available_balance = Decimal('1000.00')
        self.wallet.save()
        token, _ = Token.objects.get_or_create(user=self.user)
        self.headers = {'HTTP_AUTHORIZATION': f'Token {token.key}'}

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

        response = self.client.post(url, data, content_type='application/json', **self.headers)
        
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('500.00'))
        
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

        response = self.client.post(url, data, content_type='application/json', **self.headers)
        
        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('1000.00'))
        
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

        response = self.client.post(url, data, content_type='application/json', **self.headers)
        
        self.assertEqual(response.status_code, 202)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('500.00'))
        
        transaction = Transaction.objects.get(wallet=self.wallet)
        self.assertEqual(transaction.status, Transaction.Status.PENDING)

    @patch('finance.views.NellobyteClient.fetch_all_variations')
    def test_data_variations_success(self, mock_fetch):
        # Mock Nellobyte plans response
        mock_fetch.return_value = [
            {"ID": "1", "Name": "500MB", "Amount": "100.00"},
            {"ID": "2", "Name": "1GB", "Amount": "200.00"}
        ]

        url = reverse('data-plans')
        response = self.client.get(url, {'service_id': 'mtn-data'}, **self.headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['total_pages'], 1)
        self.assertEqual(data['page'], 1)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['results'][0]['variation_code'], "1")
        self.assertEqual(data['results'][0]['name'], "500MB")
        self.assertEqual(data['results'][0]['variation_amount'], "150.0")  # 100 + 50 profit
        self.assertEqual(data['results'][0]['type'], "Standard")

    @patch('finance.views.NellobyteClient.fetch_all_variations')
    def test_data_variations_all_providers(self, mock_fetch):
        # Same mock for all 4 providers
        mock_fetch.return_value = [
            {"ID": "1", "Name": "500MB", "Amount": "100.00"},
        ]

        url = reverse('data-plans')
        response = self.client.get(url, {'service_id': 'all'}, **self.headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should have 4 plans (one from each provider)
        self.assertEqual(data['count'], 4)
        self.assertEqual(len(data['results']), 4)
        # Each plan should have a provider label
        providers = {p['provider'] for p in data['results']}
        self.assertEqual(providers, {'MTN', 'Glo', 'Airtel', '9mobile'})

    @patch('finance.views.NellobyteClient.fetch_all_variations')
    def test_data_variations_empty_plans(self, mock_fetch):
        mock_fetch.return_value = []

        url = reverse('data-plans')
        response = self.client.get(url, {'service_id': 'mtn-data'}, **self.headers)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])


class MonnifyAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="monnify@example.com",
            username="monnifyuser",
            password="password123",
            full_name="Monnify User",
            bvn="12345678901"
        )
        self.wallet = Wallet.objects.get(user=self.user)

    @patch('finance.utils.requests.post')
    @patch('finance.utils.requests.get')
    def test_create_virtual_account_fallback_v2_url(self, mock_get, mock_post):
        """
        When Monnify says the account already exists, we fall back to listing
        reserved accounts. This test ensures the v2 URL is called and the
        correct account data is returned.
        """
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            'requestSuccessful': True,
            'responseBody': {'accessToken': 'test-token'}
        }

        create_response = MagicMock()
        create_response.json.return_value = {
            'requestSuccessful': False,
            'responseMessage': 'Already exists'
        }

        # First GET: fetch by reference returns empty (no accounts)
        fetch_response = MagicMock()
        fetch_response.json.return_value = {
            'requestSuccessful': False
        }

        # Second GET: v2 list fallback returns matching account
        list_response = MagicMock()
        list_response.json.return_value = {
            'requestSuccessful': True,
            'responseBody': {
                'content': [
                    {
                        'customerEmail': 'monnify@example.com',
                        'accounts': [
                            {
                                'bankName': 'Test Bank',
                                'accountNumber': '1234567890',
                                'bankCode': '999'
                            }
                        ]
                    }
                ]
            }
        }

        # Auth call returns token
        # Create call returns "already exists"
        # Fetch-by-reference call returns empty
        # List fallback call returns matching account
        mock_post.return_value = auth_response
        mock_get.side_effect = [fetch_response, list_response]

        # Need two post calls: auth + create
        # The first post returns auth, but we need to handle that create returns "already exists"
        # Actually the create is also a post... Let me restructure.
        # We need: post[0]=auth, post[1]=create("already exists")
        # get[0]=fetch(empty), get[1]=list(match)
        mock_post.side_effect = [auth_response, create_response]

        result, error = MonnifyAPI.create_virtual_account(self.user)

        self.assertIsNone(error)
        self.assertIsNotNone(result)
        self.assertEqual(result['bank_name'], 'Test Bank')
        self.assertEqual(result['account_number'], '1234567890')
        self.assertEqual(result['bank_code'], '999')

        # Verify the v2 URL was used for the listing fallback
        list_call_args = mock_get.call_args_list[1][0][0]
        self.assertIn('/api/v2/bank-transfer/reserved-accounts?page=0&size=50', list_call_args)

    @patch('finance.utils.requests.post')
    @patch('finance.utils.requests.get')
    def test_create_virtual_account_fetch_by_reference_success(self, mock_get, mock_post):
        """
        When the account already exists, the first attempt fetches by reference.
        If it succeeds, we return that data without hitting the v2 list fallback.
        """
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.json.return_value = {
            'requestSuccessful': True,
            'responseBody': {'accessToken': 'test-token'}
        }

        create_response = MagicMock()
        create_response.json.return_value = {
            'requestSuccessful': False,
            'responseMessage': 'Duplicate reference'
        }

        fetch_response = MagicMock()
        fetch_response.json.return_value = {
            'requestSuccessful': True,
            'responseBody': {
                'accounts': [
                    {
                        'bankName': 'GTBank',
                        'accountNumber': '0123456789',
                        'bankCode': '058'
                    }
                ]
            }
        }

        mock_post.side_effect = [auth_response, create_response]
        mock_get.return_value = fetch_response

        result, error = MonnifyAPI.create_virtual_account(self.user)

        self.assertIsNone(error)
        self.assertEqual(result['bank_name'], 'GTBank')
        self.assertEqual(result['account_number'], '0123456789')

        # Ensure the list fallback was NOT called
        self.assertEqual(mock_get.call_count, 1)
        fetch_url = mock_get.call_args[0][0]
        self.assertIn('/api/v2/bank-transfer/reserved-accounts/', fetch_url)
        self.assertNotIn('page=', fetch_url)

    @patch('finance.utils.requests.post')
    def test_create_virtual_account_auth_failure(self, mock_post):
        """If auth fails, we return None and an error message."""
        auth_response = MagicMock()
        auth_response.status_code = 401
        auth_response.json.return_value = {}

        mock_post.return_value = auth_response

        result, error = MonnifyAPI.create_virtual_account(self.user)
        self.assertIsNone(result)
        self.assertEqual(error, "Auth Failed")


class WithdrawalRequestTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="withdraw@example.com",
            username="withdrawuser",
            password="password123",
            full_name="Withdraw User"
        )
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet.available_balance = Decimal('5000.00')
        self.wallet.save()
        self.client.force_authenticate(user=self.user)
        self.headers = {'content_type': 'application/json'}

    def test_withdrawal_request_success(self):
        """Creates a PENDING ticket without disbursing funds."""
        url = reverse('withdraw')
        data = {
            'amount': '2000.00',
            'bank_code': '058',
            'bank_name': 'GTBank',
            'account_number': '0123456789',
            'account_name': 'Withdraw User',
        }
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body['status'], 'pending')

        from .models import WithdrawalTicket
        ticket = WithdrawalTicket.objects.get(pk=body['ticket_id'])
        self.assertEqual(ticket.status, WithdrawalTicket.StatusChoices.PENDING)
        self.assertEqual(ticket.amount, Decimal('2000.00'))
        self.assertEqual(ticket.account_number, '0123456789')
        self.assertEqual(ticket.bank_code, '058')

        # Balance should NOT be deducted yet
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.available_balance, Decimal('5000.00'))

    def test_withdrawal_request_missing_fields(self):
        """Returns 400 when required fields are missing."""
        url = reverse('withdraw')
        response = self.client.post(url, {'amount': '1000'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_withdrawal_request_insufficient_balance(self):
        """Returns 400 when balance is too low."""
        url = reverse('withdraw')
        data = {
            'amount': '10000.00',
            'bank_code': '058',
            'account_number': '0123456789',
        }
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn('Insufficient', body['error'])

    def test_withdrawal_request_zero_amount(self):
        """Returns 400 for zero or negative amounts."""
        url = reverse('withdraw')
        data = {
            'amount': '0',
            'bank_code': '058',
            'account_number': '0123456789',
        }
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_withdrawal_request_unauthenticated(self):
        """Returns 401 for unauthenticated requests."""
        self.client.force_authenticate(user=None)
        url = reverse('withdraw')
        data = {
            'amount': '1000',
            'bank_code': '058',
            'account_number': '0123456789',
        }
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 401)
