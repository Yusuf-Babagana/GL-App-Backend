from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Address

User = get_user_model()


class AddressBookTests(TestCase):
    """
    Covers the address book endpoints backing the mobile app's
    hooks/useAddressess.ts, which previously had no matching backend route
    at all (every call 404'd).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@example.com", password="pw12345!", full_name="Buyer One",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="pw12345!", full_name="Other User",
        )
        self.client = APIClient()
        access_token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_list_empty(self):
        response = self.client.get("/api/users/addresses")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["addresses"], [])

    def test_create_address_with_camel_case_payload(self):
        response = self.client.post("/api/users/addresses", {
            "label": "Home",
            "fullName": "Buyer One",
            "streetAddress": "1 Test Road",
            "city": "Kano",
            "state": "Kano",
            "zipCode": "700001",
            "phoneNumber": "08000000000",
            "country": "Nigeria",
            "isDefault": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        addresses = response.data["addresses"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]["fullName"], "Buyer One")
        self.assertEqual(addresses[0]["streetAddress"], "1 Test Road")
        self.assertTrue(addresses[0]["isDefault"])
        self.assertIn("_id", addresses[0])

    def test_update_address(self):
        address = Address.objects.create(
            user=self.user, label="Home", full_name="Buyer One",
            street_address="1 Test Road", city="Kano", state="Kano",
            zip_code="700001", phone_number="08000000000",
        )
        response = self.client.put(f"/api/users/addresses/{address.id}", {
            "city": "Lagos",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        address.refresh_from_db()
        self.assertEqual(address.city, "Lagos")

    def test_delete_address(self):
        address = Address.objects.create(
            user=self.user, label="Home", full_name="Buyer One",
            street_address="1 Test Road", city="Kano", state="Kano",
            zip_code="700001", phone_number="08000000000",
        )
        response = self.client.delete(f"/api/users/addresses/{address.id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Address.objects.filter(id=address.id).count(), 0)

    def test_cannot_update_or_delete_another_users_address(self):
        other_address = Address.objects.create(
            user=self.other_user, label="Home", full_name="Other User",
            street_address="2 Other Road", city="Kano", state="Kano",
            zip_code="700001", phone_number="08011111111",
        )
        put_response = self.client.put(f"/api/users/addresses/{other_address.id}", {
            "city": "Lagos",
        }, format="json")
        self.assertEqual(put_response.status_code, 404)

        delete_response = self.client.delete(f"/api/users/addresses/{other_address.id}")
        self.assertEqual(delete_response.status_code, 404)

        other_address.refresh_from_db()
        self.assertEqual(other_address.city, "Kano")

    def test_setting_new_default_clears_previous_default(self):
        first = Address.objects.create(
            user=self.user, label="Home", full_name="Buyer One",
            street_address="1 Test Road", city="Kano", state="Kano",
            zip_code="700001", phone_number="08000000000", is_default=True,
        )
        response = self.client.post("/api/users/addresses", {
            "label": "Office",
            "fullName": "Buyer One",
            "streetAddress": "5 Work Ave",
            "city": "Kano",
            "state": "Kano",
            "zipCode": "700002",
            "phoneNumber": "08000000001",
            "isDefault": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

        first.refresh_from_db()
        self.assertFalse(first.is_default)
