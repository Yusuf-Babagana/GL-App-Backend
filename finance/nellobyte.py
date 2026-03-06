import requests
from django.conf import settings

class NellobyteClient:
    def __init__(self):
        self.base_url = settings.NELLOBYTE_BASE_URL
        self.user_id = settings.NELLOBYTE_USER_ID
        self.api_key = settings.NELLOBYTE_API_KEY

    def _get_network_code(self, service_id):
        """Maps frontend service IDs to Nellobyte numeric codes"""
        mapping = {
            'mtn-data': '01',
            'glo-data': '02',
            'airtel-data': '03',
            '9mobile-data': '04',
        }
        return mapping.get(service_id.lower(), '01')

    def purchase_data(self, request_id, service_id, data_plan, phone, callback_url=""):
        endpoint = f"{self.base_url}/APIDatabundleV1.asp"
        
        params = {
            "UserID": self.user_id,
            "APIKey": self.api_key,
            "MobileNetwork": self._get_network_code(service_id),
            "DataPlan": data_plan,
            "MobileNumber": phone,
            "RequestID": request_id,
            "CallBackURL": callback_url
        }

        # Nellobyte uses HTTPS GET as per documentation
        response = requests.get(endpoint, params=params, timeout=30)
        
        # Nellobyte returns JSON. Note: Check if they return a 200 even on API failure
        return response.json()

    def query_transaction(self, request_id):
        endpoint = f"{self.base_url}/APIQueryV1.asp"
        params = {
            "UserID": self.user_id,
            "APIKey": self.api_key,
            "OrderID": request_id # Nellobyte usually checks by RequestID/OrderID
        }
        response = requests.get(endpoint, params=params, timeout=30)
        return response.json()
