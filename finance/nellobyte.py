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

    # Maps app-friendly network key to the key used in the V2 API response
    NETWORK_KEY_MAP = {
        'MTN':     'MTN',
        'Glo':     'Glo',
        'Airtel':  'Airtel',
        '9mobile': 'm_9mobile',
    }

    def fetch_all_variations(self, network_key):
        """
        Fetches all available plans for a specific network using the V2 plans endpoint.

        network_key: one of 'MTN', 'Glo', 'Airtel', '9mobile'

        The V2 endpoint returns:
        {
            "MOBILE_NETWORK": {
                "MTN":      [{ "ID": "01", "PRODUCT": [...] }],
                "Glo":      [{ "ID": "02", "PRODUCT": [...] }],
                "m_9mobile":[{ "ID": "03", "PRODUCT": [...] }],
                "Airtel":   [{ "ID": "04", "PRODUCT": [...] }],
            }
        }
        Each PRODUCT item has: PRODUCT_ID, PRODUCT_NAME, PRODUCT_AMOUNT, PRODUCT_CODE
        """
        url = f"{self.base_url}/APIDatabundlePlansV2.asp?UserID={self.user_id}"

        try:
            response = requests.get(url, timeout=20)
            data = response.json()

            mobile_networks = data.get('MOBILE_NETWORK', {})
            api_key = self.NETWORK_KEY_MAP.get(network_key, network_key)
            network_entries = mobile_networks.get(api_key, [])

            if not network_entries:
                print(f"[Nellobyte] No entries found for network '{network_key}' (api_key='{api_key}'). "
                      f"Available keys: {list(mobile_networks.keys())}")
                return []

            # Each entry is { "ID": "01", "PRODUCT": [...] }
            products = network_entries[0].get('PRODUCT', [])
            return products

        except Exception as e:
            print(f"[Nellobyte] fetch_all_variations error for '{network_key}': {e}")
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
