import requests
from django.conf import settings

class NellobyteClient:
    def __init__(self):
        self.user_id = settings.NELLOBYTE_USER_ID
        self.api_key = settings.NELLOBYTE_API_KEY
        self.base_url = "https://www.nellobytesystems.com"

    def _get_network_code(self, service_id):
        """Maps your app strings to Nellobyte numeric codes"""
        mapping = {
            'mtn-data': '01',
            'glo-data': '02',
            '9mobile-data': '03',
            'airtel-data': '04'
        }
        return mapping.get(service_id.lower(), '01')

    def fetch_all_variations(self, network_id):
        """
        Fetches all available plans for a specific network (1=MTN, 2=Glo, etc.)
        """
        # Endpoint varies; usually: APIPackage.asp or APIDataPlan.asp
        url = f"{self.base_url}/APIDataPlan.asp?UserID={self.user_id}&APIKey={self.api_key}&Network={network_id}"
        
        try:
            response = requests.get(url, timeout=20)
            data = response.json()
            # Nellobyte often returns plans under a 'dataplan' or 'packages' key
            # But the new V1/V2 structure sometimes uses different keys. We'll stick to 'dataplan' as requested.
            return data.get('DATAPLAN', data.get('dataplan', []))
        except Exception as e:
            print(f"Nellobyte Fetch Error: {e}")
            return []

    def purchase_data(self, request_id, service_id, data_plan, phone):
        url = f"{self.base_url}/APIDatabundleV1.asp"
        params = {
            "UserID": self.user_id,
            "APIKey": self.api_key,
            "MobileNetwork": self._get_network_code(service_id),
            "DataPlan": data_plan,
            "MobileNumber": phone,
            "RequestID": request_id,
            "CallBackURL": "https://glappbackend.pythonanywhere.com/api/finance/nellobyte-callback/"
        }
        
        # Nellobyte uses HTTPS GET
        response = requests.get(url, params=params, timeout=30)
        return response.json()

    def query_transaction(self, order_id=None, request_id=None):
        """Allows verification by either OrderID or RequestID"""
        url = f"{self.base_url}/APIQueryV1.asp"
        params = {
            "UserID": self.user_id,
            "APIKey": self.api_key,
        }
        if order_id:
            params["OrderID"] = order_id
        else:
            params["RequestID"] = request_id
            
        response = requests.get(url, params=params, timeout=30)
        return response.json()

    def create_reserved_account(self, user_full_name, user_email, user_phone):
        """
        Calls Nellobyte to create a dedicated virtual account for a customer.
        """
        url = f"{self.base_url}/APIGenerateVirtualAccountV1.asp"
        params = {
            "UserID": self.user_id,
            "APIKey": self.api_key,
            "CustomerName": user_full_name,
            "CustomerEmail": user_email,
            "CustomerPhone": user_phone,
        }
        try:
            response = requests.get(url, params=params, timeout=20)
            return response.json()
        except Exception as e:
            print(f"NELLOBYTE VIRTUAL ACCOUNT ERROR: {e}")
            return None
