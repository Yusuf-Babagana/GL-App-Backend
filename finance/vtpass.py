# finance/vtpass.py
import requests
from django.conf import settings

class VTPassClient:
    def get_data_plans(self, service_id):
        """service_id examples: mtn-data, glo-data, airtel-data"""
        url = f"{settings.VTPASS_BASE_URL}/service-variations?serviceID={service_id}"
        response = requests.get(url)
        return response.json()

    def purchase_data(self, request_id, service_id, variation_code, phone, amount):
        url = f"{settings.VTPASS_BASE_URL}/pay"
        
        # VTpass expects these specific keys
        payload = {
            "request_id": request_id,
            "serviceID": service_id,
            "variation_code": variation_code,
            "phone": phone,
            "billersCode": phone, # Some services require this specifically
            "amount": float(amount)
        }
        
        headers = {
            "api-key": settings.VTPASS_API_KEY,
            "secret-key": settings.VTPASS_SECRET_KEY,
            "Content-Type": "application/json"
        }

        # Use json=payload to ensure it's sent as a JSON string
        response = requests.post(url, json=payload, headers=headers)
        return response.json()