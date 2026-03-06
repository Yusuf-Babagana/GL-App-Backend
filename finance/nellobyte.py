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

    def fetch_plans(self, network_code):
        """Fetch real-time plans from Nellobyte"""
        url = f"{self.base_url}/APIDatabundlePlansV2.asp?UserID={self.user_id}"
        try:
            resp = requests.get(url, timeout=20)
            data = resp.json()
            
            # DEBUG: See the actual keys Nellobyte is sending
            print(f"DEBUG NELLOBYTE DATA: {data.keys()}") 
            
            # Nellobyte often uses 'mobile_data' or 'content' as the root key
            # Let's adjust the extraction logic to be more flexible
            content = data.get("content", data) 
            
            network_name_map = {"01": "MTN", "02": "Glo", "03": "9mobile", "04": "Airtel"}
            network_key = network_name_map.get(network_code)
            
            # Try to find the network key regardless of case
            plans = []
            if isinstance(content, dict):
                for key in content.keys():
                    if key.upper() == network_key.upper():
                        plans = content[key]
                        break
            
            print(f"DEBUG FOUND PLANS FOR {network_key}: {len(plans)}")            
            return plans
        except Exception as e:
            print(f"Nellobyte Plan Fetch Error: {e}")
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
