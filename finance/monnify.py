import requests
import base64
from django.conf import settings

class MonnifyClient:
    def __init__(self):
        # We will point these to your settings.py later
        self.api_key = getattr(settings, "MONNIFY_API_KEY", "YOUR_API_KEY")
        self.secret_key = getattr(settings, "MONNIFY_SECRET_KEY", "YOUR_SECRET_KEY")
        self.contract_code = getattr(settings, "MONNIFY_CONTRACT_CODE", "YOUR_CONTRACT_CODE")
        self.base_url = getattr(settings, "MONNIFY_BASE_URL", "https://api.monnify.com/api/v1")

    def get_access_token(self):
        """Auth with Monnify to get a session token"""
        auth_str = f"{self.api_key}:{self.secret_key}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {"Authorization": f"Basic {encoded_auth}"}
        response = requests.post(f"{self.base_url}/auth/login", headers=headers)
        
        if response.status_code == 200:
            return response.json()['responseBody']['accessToken']
        
        # ADD THIS: This will tell us if your keys are wrong
        print(f"!!! Monnify Auth Error: {response.status_code} - {response.text}")
        return None

    def generate_virtual_account(self, user_full_name, user_email, account_reference):
        """Request a dedicated virtual account for a user"""
        token = self.get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "accountReference": account_reference,
            "accountName": user_full_name,
            "currencyCode": "NGN",
            "contractCode": self.contract_code,
            "customerEmail": user_email,
            "customerName": user_full_name,
            "getAllAvailableBanks": True # Gives the user multiple bank options
        }

        response = requests.post(f"{self.base_url}/bank-transfer/reserved-accounts", headers=headers, json=data)
        
        # ADD THIS: This will show if the Contract Code or Account Ref is the issue
        print(f"!!! Monnify Account Creation Response: {response.json()}")
        return response.json()

    def initiate_withdrawal(self, amount, reference, bank_code, account_number, narration):
        """Transfer funds from your merchant balance to a user's bank account"""
        token = self.get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "amount": float(amount),
            "reference": reference,
            "narration": narration,
            "destinationBankCode": bank_code,
            "destinationAccountNumber": account_number,
            "currency": "NGN",
            "sourceAccountNumber": "YOUR_MONNIFY_WALLET_ID" # Found in your Monnify dashboard
        }

        response = requests.post(f"{self.base_url}/disbursements/single", headers=headers, json=data)
        return response.json()

    def verify_bank_account(self, account_number, bank_code):
        """Verifies the account number and returns the account name"""
        token = self.get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "accountNumber": account_number,
            "bankCode": bank_code
        }

        # Monnify endpoint for account validation
        response = requests.get(
            f"{self.base_url}/bank-transfer/reserved-accounts/lookup", 
            headers=headers, 
            params=params
        )
        
        if response.status_code == 200:
            return response.json().get('responseBody') # Contains 'accountName'
        return None

    def get_reserved_account_details(self, account_reference):
        """Fetch details of a reserved account by account reference or email"""
        token = self.get_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        # The user's snippet uses /api/v1/... but our base_url already includes it
        # However, to be safe, I'll use the existing pattern for now
        url = f"{self.base_url}/bank-transfer/reserved-accounts/{account_reference}"
        response = requests.get(url, headers=headers)
        return response.json()