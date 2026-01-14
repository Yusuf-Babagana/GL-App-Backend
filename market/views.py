from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from rest_framework import generics, permissions, status, filters, views
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers 

# Local Imports
from .models import Category, Store, Product, Order, OrderItem, Cart, CartItem
from .serializers import (
    CategorySerializer, StoreSerializer, ProductSerializer, 
    OrderSerializer, CartSerializer
)
from finance.models import Wallet, Transaction

# --- SELLER / STORE VIEWS ---

class StoreCreateView(generics.CreateAPIView):
    """ Allows a user to create their own store """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        
        # Auto-update user role
        if self.request.user.roles is None:
             self.request.user.roles = []
        if 'seller' not in self.request.user.roles:
            self.request.user.roles.append('seller')
        self.request.user.active_role = 'seller'
        self.request.user.save()

class SellerProductListView(generics.ListAPIView):
    """ Lists only products belonging to the logged-in seller """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user).order_by('-created_at')

class ProductCreateView(generics.CreateAPIView):
    """ Allows a seller to add a new product """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        try:
            store = Store.objects.get(owner=self.request.user)
            serializer.save(store=store)
        except Store.DoesNotExist:
            raise serializers.ValidationError("You must create a store first.")

# --- PUBLIC BROWSING ---

class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'category__name']

class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

# --- SELLER DASHBOARD (Alternative Implementation) ---

class CreateStoreView(generics.CreateAPIView):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class SellerProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not hasattr(self.request.user, 'store'):
            return Product.objects.none()
        return Product.objects.filter(store=self.request.user.store)

    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'store'):
            raise permissions.PermissionDenied("You must open a store first.")
        serializer.save(store=self.request.user.store)


# --- CART & ORDERING ---

class CartAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, request):
        cart, created = Cart.objects.get_or_create(user=request.user)
        return cart

    def get(self, request):
        cart = self.get_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    def post(self, request):
        cart = self.get_cart(request)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        if not product_id:
            return Response({"error": "Product ID required"}, status=status.HTTP_400_BAD_REQUEST)

        product = get_object_or_404(Product, id=product_id)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)

        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity
        cart_item.save()

        return Response({"message": "Item added to cart"}, status=status.HTTP_200_OK)

    def delete(self, request):
        item_id = request.data.get('item_id')
        if not item_id:
             return Response({"error": "Item ID required"}, status=status.HTTP_400_BAD_REQUEST)

        deleted_count, _ = CartItem.objects.filter(id=item_id, cart__user=request.user).delete()
        if deleted_count > 0:
            return Response({"message": "Item removed"}, status=status.HTTP_200_OK)
        return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)


class CreateOrderView(APIView):
    """
    Handles Checkout: Checks Wallet Balance, Locks Funds, Creates Order.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            cart = Cart.objects.get(user=request.user)
            wallet = Wallet.objects.get(user=request.user)
        except Cart.DoesNotExist:
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
        except Wallet.DoesNotExist:
            return Response({"error": "Wallet not found"}, status=status.HTTP_400_BAD_REQUEST)

        if not cart.items.exists():
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Calculate Total (Manually to avoid missing attribute errors)
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())

        # 2. Check Funds
        if wallet.balance < cart_total:
            return Response({
                "error": "Insufficient Funds", 
                "balance": wallet.balance,
                "required": cart_total
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Process Order (Atomic)
        with transaction.atomic():
            # Deduct & Lock
            wallet.balance -= cart_total
            wallet.escrow_balance += cart_total
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=-cart_total,
                transaction_type='escrow_lock',
                status='success',
                description="Payment for Order (Locked)"
            )

            # Create Order
            order = Order.objects.create(
                buyer=request.user,
                store=cart.items.first().product.store,
                total_price=cart_total,
                shipping_address_json=request.data.get('shipping_address', {}),
                payment_status='escrow_held',
                delivery_status='pending'
            )

            # Move Items
            items_to_create = []
            for cart_item in cart.items.all():
                items_to_create.append(OrderItem(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price_at_purchase=cart_item.product.price
                ))
            OrderItem.objects.bulk_create(items_to_create)

            # Clear Cart
            cart.items.all().delete()

        return Response({
            "message": "Order placed successfully. Funds held in Escrow.", 
            "order_id": order.id
        }, status=status.HTTP_201_CREATED)


class BuyerOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user).order_by('-created_at')

class BuyerOrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user)

class ConfirmOrderReceiptView(APIView):
    """
    Buyer confirms receipt -> Funds moved from Escrow to Seller.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)

        if order.payment_status == 'released':
            return Response({"error": "Funds already released."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # 1. Update Status
            order.payment_status = 'released'
            order.delivery_status = 'delivered'
            order.save()

            # 2. Unlock Funds (Remove from Buyer Escrow)
            buyer_wallet = request.user.wallet
            # Force conversion to Decimal to prevent "float" errors
            current_escrow = Decimal(str(buyer_wallet.escrow_balance))
            buyer_wallet.escrow_balance = current_escrow - order.total_price
            buyer_wallet.save()

            # 3. Pay Seller (90% Share)
            seller_share = order.total_price * Decimal('0.90')
            
            seller_wallet, _ = Wallet.objects.get_or_create(user=order.store.owner)
            
            # FIX: Convert the seller's current balance to Decimal before adding
            current_seller_balance = Decimal(str(seller_wallet.balance))
            seller_wallet.balance = current_seller_balance + seller_share
            seller_wallet.save()

            Transaction.objects.create(
                wallet=seller_wallet,
                amount=seller_share,
                transaction_type='payment',
                status='success',
                description=f"Earnings for Order #{order.id}"
            )

        return Response({"message": "Delivery confirmed. Funds released to Seller."}, status=status.HTTP_200_OK)



class SellerOrderListView(generics.ListAPIView):
    """
    List orders that contain items from the logged-in user's store.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Find the store owned by this user
        # Then find orders linked to that store
        return Order.objects.filter(store__owner=self.request.user).order_by('-created_at')

class SellerDashboardStatsView(APIView):
    """
    Returns simple stats for the dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            store = Store.objects.get(owner=request.user)
            products_count = Product.objects.filter(store=store).count()
            # Count orders for this store
            orders_count = Order.objects.filter(store=store).count()
            # Calculate Revenue (Sum of delivered orders)
            revenue = Order.objects.filter(store=store, delivery_status='delivered').aggregate(total=models.Sum('total_price'))['total'] or 0
            
            return Response({
                "products": products_count,
                "orders": orders_count,
                "revenue": revenue,
                "store_name": store.name
            })
        except Store.DoesNotExist:
            return Response({"error": "No store found"}, status=404)