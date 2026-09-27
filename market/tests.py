from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from finance.models import Wallet
from .models import Shop, Product, Order, WishlistItem

User = get_user_model()


def _auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class MultiShopCheckoutTests(TestCase):
    """
    A cart spanning two different sellers' shops must produce one Order per
    shop, each visible only to its own seller, with escrow credited to the
    correct seller for the correct amount.
    """

    def setUp(self):
        self.buyer = User.objects.create_user(
            email="buyer@example.com", password="pw12345!", full_name="Buyer One",
        )
        self.buyer.set_transaction_pin("1234")
        self.buyer.save()

        self.seller_a = User.objects.create_user(
            email="seller_a@example.com", password="pw12345!", full_name="Seller A",
        )
        self.seller_b = User.objects.create_user(
            email="seller_b@example.com", password="pw12345!", full_name="Seller B",
        )

        self.shop_a = Shop.objects.create(owner=self.seller_a, name="Shop A", is_active=True)
        self.shop_b = Shop.objects.create(owner=self.seller_b, name="Shop B", is_active=True)

        self.product_a = Product.objects.create(
            shop=self.shop_a, name="Widget A", description="x", price=Decimal("1000.00"), stock=10,
        )
        self.product_b = Product.objects.create(
            shop=self.shop_b, name="Widget B", description="x", price=Decimal("500.00"), stock=10,
        )

        buyer_wallet, _ = Wallet.objects.get_or_create(user=self.buyer)
        buyer_wallet.available_balance = Decimal("2000.00")
        buyer_wallet.save()

        self.client = _auth_client(self.buyer)

    def _checkout(self, pin="1234"):
        return self.client.post("/api/market/checkout/", {
            "items": [
                {"product_id": self.product_a.id, "quantity": 1},
                {"product_id": self.product_b.id, "quantity": 1},
            ],
            "payment_method": "wallet",
            "shipping_address": {"address": "1 Test Rd", "city": "Kano", "phone": "0800"},
            "pin": pin,
        }, format="json")

    def test_checkout_without_pin_is_rejected(self):
        response = self._checkout(pin="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_with_wrong_pin_is_rejected(self):
        response = self._checkout(pin="0000")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_multi_shop_cart_creates_one_order_per_shop(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 201, response.data)

        orders = list(Order.objects.filter(buyer=self.buyer))
        self.assertEqual(len(orders), 2)

        order_a = Order.objects.get(shop=self.shop_a)
        order_b = Order.objects.get(shop=self.shop_b)
        self.assertEqual(order_a.total_price, Decimal("1000.00"))
        self.assertEqual(order_b.total_price, Decimal("500.00"))
        self.assertEqual(order_a.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order_b.payment_status, Order.PaymentStatus.PAID)

        # Buyer wallet debited the combined total exactly once.
        self.buyer.wallet.refresh_from_db()
        self.assertEqual(self.buyer.wallet.available_balance, Decimal("500.00"))

        # Each seller's escrow reflects only their own order's amount.
        self.seller_a.wallet.refresh_from_db()
        self.seller_b.wallet.refresh_from_db()
        self.assertEqual(self.seller_a.wallet.locked_balance, Decimal("1000.00"))
        self.assertEqual(self.seller_b.wallet.locked_balance, Decimal("500.00"))

        # Each seller sees only their own order in their dashboard.
        seller_a_client = _auth_client(self.seller_a)
        resp_a = seller_a_client.get("/api/market/seller/orders/")
        self.assertEqual(resp_a.status_code, 200)
        seller_a_order_ids = {o["id"] for o in resp_a.data["results"]} if "results" in resp_a.data else {o["id"] for o in resp_a.data}
        self.assertIn(order_a.id, seller_a_order_ids)
        self.assertNotIn(order_b.id, seller_a_order_ids)

    def test_buyer_can_independently_confirm_each_shops_order(self):
        self._checkout()
        order_a = Order.objects.get(shop=self.shop_a)
        order_b = Order.objects.get(shop=self.shop_b)

        resp = self.client.post(f"/api/market/buyer/orders/{order_a.id}/confirm/")
        self.assertEqual(resp.status_code, 200, resp.data)

        self.seller_a.wallet.refresh_from_db()
        self.seller_b.wallet.refresh_from_db()
        # Seller A's escrow released (minus commission); Seller B's untouched.
        self.assertEqual(self.seller_a.wallet.locked_balance, Decimal("0.00"))
        self.assertGreater(self.seller_a.wallet.available_balance, Decimal("0.00"))
        self.assertEqual(self.seller_b.wallet.locked_balance, Decimal("500.00"))

        order_b.refresh_from_db()
        self.assertEqual(order_b.payment_status, Order.PaymentStatus.PAID)


class WishlistTests(TestCase):
    """
    Covers /api/users/wishlist and /api/users/wishlist/<product_id>, backing
    hooks/useWishlist.ts -- there was previously no backend for this at all
    (every call from the live wishlist screen 404'd).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="buyer@example.com", password="pw12345!", full_name="Buyer One",
        )
        seller = User.objects.create_user(
            email="seller@example.com", password="pw12345!", full_name="Seller One",
        )
        shop = Shop.objects.create(owner=seller, name="Shop A", is_active=True)
        self.product = Product.objects.create(
            shop=shop, name="Widget", description="x", price=Decimal("1500.50"), stock=5,
        )
        self.client = _auth_client(self.user)

    def test_add_and_list_wishlist(self):
        response = self.client.post("/api/users/wishlist", {"productId": self.product.id}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        wishlist = response.data["wishlist"]
        self.assertEqual(len(wishlist), 1)
        self.assertEqual(wishlist[0]["_id"], str(self.product.id))
        self.assertEqual(wishlist[0]["name"], "Widget")
        self.assertEqual(wishlist[0]["price"], 1500.5)
        self.assertEqual(wishlist[0]["stock"], 5)

        get_response = self.client.get("/api/users/wishlist")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(len(get_response.data["wishlist"]), 1)

    def test_adding_same_product_twice_is_idempotent(self):
        self.client.post("/api/users/wishlist", {"productId": self.product.id}, format="json")
        response = self.client.post("/api/users/wishlist", {"productId": self.product.id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data["wishlist"]), 1)
        self.assertEqual(WishlistItem.objects.filter(user=self.user).count(), 1)

    def test_remove_from_wishlist(self):
        WishlistItem.objects.create(user=self.user, product=self.product)
        response = self.client.delete(f"/api/users/wishlist/{self.product.id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["wishlist"], [])
        self.assertEqual(WishlistItem.objects.filter(user=self.user).count(), 0)

    def test_wishlist_is_per_user(self):
        other_user = User.objects.create_user(
            email="other@example.com", password="pw12345!", full_name="Other",
        )
        WishlistItem.objects.create(user=other_user, product=self.product)

        response = self.client.get("/api/users/wishlist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["wishlist"], [])
