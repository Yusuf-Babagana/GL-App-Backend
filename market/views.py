import base64
import uuid as uuid_lib
import logging
from decimal import Decimal
from collections import defaultdict
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction, models
from django.db.models import Q, Sum
from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import serializers 
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Financial Constants
# ---------------------------------------------------------------------------
GLAPP_COMMISSION_RATE = Decimal('0.05')
GLAPP_COMMISSION_CAP  = Decimal('2500.00')
# ---------------------------------------------------------------------------

# Local Imports
from .models import Category, Shop, Product, Order, OrderItem, Cart, CartItem, ProductImage, MerchantProfile
from .serializers import (
    CategorySerializer, ShopSerializer, ProductSerializer, 
    OrderSerializer, CartSerializer, CartSyncInputSerializer,
    CartSyncItemSerializer, CartSyncResponseSerializer,
)
from finance.models import Wallet, Transaction, PlatformRevenue


# --- SELLER / STORE VIEWS ---

class ShopCreateView(generics.CreateAPIView):
    """ Allows a user to create their own shop """
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    # --- DEBUGGING FIX: Override POST to see errors ---
    def post(self, request, *args, **kwargs):
        print("Received Shop Data:", request.data) # <--- Debug Print
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            print("Validation Errors:", serializer.errors) # <--- Debug Print
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        
        # Auto-update user role
        if self.request.user.roles is None:
             self.request.user.roles = []
        if 'seller' not in self.request.user.roles:
            self.request.user.roles.append('seller')
        self.request.user.active_role = 'seller'
        self.request.user.save()

class MerchantOnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            # Safely extract data sent from the mobile app
            data = request.data
            
            # update_or_create prevents "User already has a shop" IntegrityErrors
            shop, created = Shop.objects.update_or_create(
                owner=request.user,
                defaults={
                    'name': data.get('shop_name'),
                    'shop_type': data.get('shop_type'),
                    'id_type': data.get('id_type'),
                    'address': data.get('shop_address', ''),
                    'is_active': False  # Wait for admin review
                }
            )

            # Handle Cloudinary URL strings instead of file uploads
            if 'id_document' in request.data and request.data['id_document']:
                shop.id_document = request.data['id_document']
                shop.save()

            if 'shop_logo' in request.data and request.data['shop_logo']:
                shop.logo = request.data['shop_logo']
                shop.save()

            # 🌟 CORE ARCHITECTURAL RULE COMPLIANCE FIX:
            # Change their platform system role identity profile state to 'seller' immediately
            user_profile = request.user
            user_profile.active_role = 'seller'
            if not user_profile.roles:
                user_profile.roles = []
            if 'seller' not in user_profile.roles:
                user_profile.roles.append('seller')
            user_profile.save()

            return Response({
                "status": "success",
                "message": "Shop application registered. Awaiting admin activation.",
                "user": {
                    "email": user_profile.email,
                    "is_admin": False,
                    "role": "seller" # Sent out to refresh mobile client state cache configuration settings
                }
            }, status=201)

        except Exception as e:
            # Send the exact error string back to the phone for debugging
            print(f"ONBOARDING ERROR: {str(e)}")
            return Response({"status": "error", "message": str(e)}, status=400)


class MerchantGlobalOnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Enforce multi-part parser so binary images parse cleanly

    def post(self, request):
        user = request.user
        data = request.data

        # 🛡️ Prevent duplicate store entries for the same account profile
        if Shop.objects.filter(owner=user).exists():
            return Response({
                "status": "error", 
                "message": "An active registration file already exists for this account profile."
            }, status=400)

        try:
            # 🌟 CORE ARCHITECTURAL RULE COMPLIANCE:
            # Change their platform system role identity profile state to 'seller' immediately
            user.active_role = 'seller'
            if not user.roles:
                user.roles = []
            if 'seller' not in user.roles:
                user.roles.append('seller')
            user.save()

            # Create the record matching the exact multi-part keys shipped by Axios/FormData
            shop = Shop.objects.create(
                owner=user,
                # Step 1 Personal Info keys fallback map
                owner_full_name=data.get('owner_name') or data.get('name'),
                owner_email=data.get('owner_email') or data.get('email') or user.email,
                owner_phone=data.get('owner_phone') or data.get('phone'),
                id_type=data.get('id_type') or data.get('idType'),
                id_number=data.get('id_number') or data.get('idNumber'),
                id_image=request.FILES.get('id_image'),
                id_document=request.FILES.get('id_image'),   # Backward compatibility fallback

                # Step 2 Shop Info keys fallback map
                name=data.get('shop_name') or data.get('shopName'),
                shop_type=data.get('shop_type') or data.get('shopType'),
                business_phone=data.get('business_phone') or data.get('businessPhone'),
                address=data.get('shop_address') or data.get('shopAddress'),
                state=data.get('state', 'Kano'),
                logo=request.FILES.get('logo'),

                # Legal registry data
                is_registered=str(data.get('registered', 'no')).lower() == 'yes',
                cac_number=data.get('cac_number', ''),
                is_active=False # Keep pending until approved!
            )

            return Response({
                "status": "success", 
                "message": "Application file received and locked for administrative verification."
            }, status=201)

        except Exception as e:
            return Response({
                "status": "error", 
                "message": f"Database parsing failed structural rules: {str(e)}"
            }, status=400)


class AdminOverviewTelemetryView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request):
        """
        Populates your administration grid tracking summary lists dynamically.
        """
        total_users = User.objects.count()
        pending_shops = Shop.objects.filter(is_active=False).select_related('owner')
        
        shops_payload = [{
            "id": str(shop.id), # UUID converted to string safely
            "name": shop.name,
            "shop_type": shop.shop_type,
            "owner_email": shop.owner.email,
            "owner_name": shop.owner_full_name or shop.owner.get_full_name() or '',
            "id_type": shop.id_type,
            "id_number": shop.id_number
        } for shop in pending_shops]

        users_payload = [{
            "id": u.pk,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "role": getattr(u, 'active_role', 'buyer') or 'buyer'
        } for u in User.objects.all()]

        return Response({
            "pending_shops": shops_payload,
            "users": users_payload,
            "metrics": {
                "total_users": total_users,
                "pending_count": len(shops_payload)
            }
        }, status=200)


class ShopStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            shop = Shop.objects.get(owner=request.user)
            
            # Safely handle default values if fields are missing in the DB row
            return Response({
                "exists": True,
                "is_active": getattr(shop, 'is_active', False),
                "shop_name": getattr(shop, 'name', 'Unnamed Store') or 'Unnamed Store',
                "shop_type": getattr(shop, 'shop_type', ''),
                "total_sales": getattr(shop, 'total_sales', 0) or 0
            }, status=200)
            
        except Shop.DoesNotExist:
            return Response({
                "exists": False,
                "is_active": False,
                "message": "No shop found."
            }, status=200)
        except Exception as e:
            # 🔥 Catch internal bugs and return them as JSON instead of a raw 500 HTML crash
            return Response({
                "exists": False,
                "error": f"Backend Exception: {str(e)}"
            }, status=200)

class SellerProductListView(generics.ListAPIView):
    """ Lists only products belonging to the logged-in seller """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(shop__owner=self.request.user).order_by('-created_at')

class ProductCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return Response({"error": "You must create a shop first."}, status=status.HTTP_403_FORBIDDEN)
        if not shop.is_active:
            return Response({"error": "Your shop is pending activation."}, status=status.HTTP_403_FORBIDDEN)

        errors = {}

        name = request.data.get('name', '').strip()
        if not name:
            errors['name'] = 'This field is required.'

        description = request.data.get('description', '').strip()
        if not description:
            errors['description'] = 'This field is required.'

        price_raw = request.data.get('price')
        if not price_raw:
            errors['price'] = 'This field is required.'
        else:
            try:
                price = Decimal(str(price_raw))
                if price <= 0:
                    errors['price'] = 'Price must be greater than zero.'
            except Exception:
                errors['price'] = 'Invalid decimal value for price.'

        stock_raw = request.data.get('stock')
        if stock_raw is not None and stock_raw != '':
            try:
                stock = int(str(stock_raw))
                if stock < 0:
                    errors['stock'] = 'Stock cannot be negative.'
            except (ValueError, TypeError):
                errors['stock'] = 'Invalid integer value for stock.'
        else:
            stock = 1

        category_id = request.data.get('category')
        category = None
        if category_id:
            try:
                category = Category.objects.get(id=int(category_id))
            except (ValueError, TypeError, Category.DoesNotExist):
                errors['category'] = 'Invalid category identifier.'

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        image_value = ''
        if 'image' in request.FILES:
            uploaded = request.FILES['image']
            from django.core.files.storage import default_storage
            from django.utils import timezone
            ts = int(timezone.now().timestamp())
            path = default_storage.save(f'products/{ts}_{uploaded.name}', uploaded)
            image_value = default_storage.url(path)
        elif request.data.get('image'):
            image_value = request.data.get('image')

        video_value = request.data.get('video_url', '')

        image_links = request.data.get('images', [])
        if isinstance(image_links, str):
            try:
                import json
                image_links = json.loads(image_links)
            except (json.JSONDecodeError, ValueError):
                image_links = []

        try:
            product = Product.objects.create(
                shop=shop,
                name=name,
                description=description,
                price=price,
                stock=stock,
                category=category,
                image=image_value,
                video=video_value if video_value else '',
                is_ad=True,
            )

            if isinstance(image_links, list):
                for i, link in enumerate(image_links):
                    if link:
                        ProductImage.objects.create(
                            product=product,
                            image=link,
                            is_primary=(i == 0 and not image_value)
                        )

            return Response({
                "message": "Product created successfully",
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": str(product.price),
                    "stock": product.stock,
                    "image": product.image,
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": f"Failed to create product: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- PUBLIC BROWSING ---

class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

@method_decorator(cache_page(300), name='dispatch')
@method_decorator(vary_on_headers('Authorization'), name='dispatch')
class ProductListView(generics.ListAPIView):
    queryset = Product.objects.select_related('shop', 'category').prefetch_related('images')
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['price', '-price', 'created_at', '-created_at', 'name']
    ordering = ['-created_at']

class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

# --- SELLER DASHBOARD ---

class SellerProductListCreateView(generics.ListCreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not hasattr(self.request.user, 'merchant_shop'):
            return Product.objects.none()
        return Product.objects.filter(shop=self.request.user.merchant_shop)

    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'merchant_shop'):
            raise permissions.PermissionDenied("You must open a shop first.")
        serializer.save(shop=self.request.user.merchant_shop)


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


class CartSyncView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CartSyncInputSerializer(data=request.data.get('items', []), many=True)
        serializer.is_valid(raise_exception=True)

        local_items = serializer.validated_data
        product_ids = [item['product_id'] for item in local_items if item['quantity'] > 0]

        products = Product.objects.filter(id__in=product_ids).select_related('shop').prefetch_related('images')
        product_map = {p.id: p for p in products}

        cart, _ = Cart.objects.get_or_create(user=request.user)

        synced_items = []
        seen_product_ids = set()

        with transaction.atomic():
            existing_items = {ci.product_id: ci for ci in CartItem.objects.filter(cart=cart).select_related('product')}

            for item in local_items:
                pid = item['product_id']
                requested = item['quantity']

                if requested <= 0:
                    if pid in existing_items:
                        existing_items[pid].delete()
                    continue

                product = product_map.get(pid)
                if not product:
                    continue

                available = product.stock
                synced_qty = min(requested, available) if available > 0 else 0

                seen_product_ids.add(pid)

                if synced_qty > 0:
                    cart_item, _ = CartItem.objects.update_or_create(
                        cart=cart,
                        product=product,
                        defaults={'quantity': synced_qty},
                    )
                    synced_items.append(cart_item)
                else:
                    if pid in existing_items:
                        existing_items[pid].delete()

            stale_ids = set(existing_items.keys()) - seen_product_ids
            if stale_ids:
                CartItem.objects.filter(cart=cart, product_id__in=stale_ids).delete()

        augmented = []
        for ci in synced_items:
            product = ci.product
            requested = next(
                (it['quantity'] for it in local_items if it['product_id'] == product.id),
                ci.quantity,
            )
            row = {
                'product_id': product.id,
                'product': product,
                'quantity': requested,
                'synced_quantity': ci.quantity,
                'subtotal': product.price * ci.quantity,
            }
            augmented.append(row)

        total = sum(r['subtotal'] for r in augmented)
        response_data = CartSyncResponseSerializer({
            'synced_items': augmented,
            'total_price': total,
            'synced_at': timezone.now(),
        }).data

        return Response(response_data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class CreateOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        cart_items = request.data.get('items', []) # Expects [{product_id, quantity}, ...]
        if not cart_items:
            return Response({"status": "error", "message": "Your cart compilation list is completely empty."}, status=400)

        try:
            total_calculated_price = Decimal('0.00')
            order_items_to_create = []

            with transaction.atomic():
                # Loop through tracking array blocks to compute costs
                for item in cart_items:
                    product = Product.objects.select_for_update().get(id=item['product_id'])
                    qty = int(item['quantity'])
                    
                    if product.stock < qty:
                        return Response({
                            "status": "out_of_stock",
                            "product_id": product.id,
                            "available_stock": product.stock,
                            "message": f"Only {product.stock} units of {product.name} are available."
                        }, status=400)
                    
                    total_calculated_price += (product.price * qty)
                    order_items_to_create.append((product, qty))

                # Create the master order record sheet mapping instance
                # Adapted to active database mapping definitions: buyer, total_price, delivery_status, payment_status
                new_order = Order.objects.create(
                    buyer=request.user,
                    shop=order_items_to_create[0][0].shop if order_items_to_create else None,
                    total_price=total_calculated_price,
                    delivery_status=Order.DeliveryStatus.PENDING,
                    payment_status=Order.PaymentStatus.PENDING,
                    shipping_address_json=request.data.get('shipping_address', {})
                )

                # Build item splits ledger linkages
                for product, qty in order_items_to_create:
                    OrderItem.objects.create(
                        order=new_order, 
                        product=product, 
                        quantity=qty, 
                        price_at_purchase=product.price
                    )
                    product.stock -= qty # Decrement catalog stock capacity counters
                    product.save()

            return Response({
                "status": "success",
                "message": "Order reference written successfully.",
                "order_id": new_order.id,
                "amount_to_pay": total_calculated_price
            }, status=201)

        except Product.DoesNotExist:
            return Response({"status": "error", "message": "One or more chosen item references do not match our database records."}, status=404)
        except Exception as e:
            return Response({"status": "error", "message": f"Server transaction failed: {str(e)}"}, status=500)


class InternalWalletCheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == Order.PaymentStatus.PAID:
            return Response({"error": "This order has already been paid."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            buyer_wallet, _ = Wallet.objects.select_for_update().get_or_create(
                user=request.user, defaults={'available_balance': Decimal('0.00')}
            )

            if buyer_wallet.available_balance < order.total_price:
                return Response({
                    "status": "low_balance",
                    "message": f"Insufficient wallet funds. Required: ₦{order.total_price:,.0f}, Available: ₦{buyer_wallet.available_balance:,.0f}."
                }, status=status.HTTP_400_BAD_REQUEST)

            buyer_wallet.available_balance -= order.total_price
            buyer_wallet.save()

            order_items = OrderItem.objects.filter(order=order).select_related('product__shop__owner')
            merchant_shares = {}
            for item in order_items:
                owner = item.product.shop.owner
                amount = item.quantity * item.price_at_purchase
                merchant_shares[owner] = merchant_shares.get(owner, Decimal('0.00')) + amount

            for owner, amount in merchant_shares.items():
                seller_wallet, _ = Wallet.objects.select_for_update().get_or_create(
                    user=owner, defaults={'available_balance': Decimal('0.00')}
                )
                seller_wallet.locked_balance += amount
                seller_wallet.save()

                Transaction.objects.create(
                    wallet=seller_wallet,
                    amount=amount,
                    transaction_type=Transaction.TransactionType.PAYMENT,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order.id),
                    description=f"Sales earnings (locked) for Order #{order.id}"
                )

            Transaction.objects.create(
                wallet=buyer_wallet,
                amount=-order.total_price,
                transaction_type=Transaction.TransactionType.PAYMENT,
                status=Transaction.Status.SUCCESS,
                related_order_id=str(order.id),
                description=f"Payment for Order #{order.id}"
            )

            order.payment_status = Order.PaymentStatus.PAID
            order.save()

        return Response({
            "status": "success",
            "message": "Payment successful. Funds locked until buyer confirms receipt."
        }, status=status.HTTP_200_OK)


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

class BuyerConfirmReceiptView(APIView):
    """
    Buyer confirms they received the item.
    Atomically releases funds from Seller's locked_balance:
      - Platform commission is deducted and logged.
      - Net proceeds are moved to the seller's available_balance.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id, buyer=request.user)

                if order.payment_status != Order.PaymentStatus.PAID:
                    return Response({"error": "Order has not been paid yet."}, status=400)

                if order.payment_status == Order.PaymentStatus.CONFIRMED:
                    return Response({"error": "This order has already been confirmed."}, status=400)

                seller_wallet = Wallet.objects.select_for_update().get(user=order.shop.owner)

                if seller_wallet.locked_balance < order.total_price:
                    return Response({"error": "Insufficient locked balance for this order."}, status=400)

                order_total = order.total_price

                commission = min(order_total * GLAPP_COMMISSION_RATE, GLAPP_COMMISSION_CAP)
                net_payout = order_total - commission

                seller_wallet.locked_balance -= order_total
                seller_wallet.available_balance += net_payout
                seller_wallet.save()

                PlatformRevenue.add_commission(commission)

                Transaction.objects.create(
                    wallet=seller_wallet,
                    amount=net_payout,
                    transaction_type=Transaction.TransactionType.ESCROW_RELEASE,
                    status=Transaction.Status.SUCCESS,
                    related_order_id=str(order.id),
                    description=f"Funds released for Order #{order.id} (Commission: ₦{commission})"
                )

                order.payment_status = Order.PaymentStatus.CONFIRMED
                order.save()

                return Response({
                    "message": "Receipt confirmed! Funds released to seller.",
                    "net_payout": str(net_payout),
                    "commission": str(commission)
                }, status=200)

        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=404)
        except Wallet.DoesNotExist:
            return Response({"error": "Seller wallet not found."}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class SellerOrderListView(generics.ListAPIView):
    """
    List orders that contain items from the logged-in user's store.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Find the shop owned by this user
        # Then find orders linked to that shop
        return Order.objects.filter(shop__owner=self.request.user).order_by('-created_at')

class MerchantDashboardView(APIView):
    """
    Returns real-time stats for the merchant dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            shop = Shop.objects.get(owner=request.user)
            
            # Calculate real stats from the database
            total_sales = Order.objects.filter(shop=shop).aggregate(Sum('total_price'))['total_price__sum'] or 0
            total_orders = Order.objects.filter(shop=shop).count()
            new_customers = Order.objects.filter(shop=shop).values('buyer').distinct().count()

            return Response({
                "shop_name": shop.name,
                "stats": {
                    "total_sales": f"N{total_sales}",
                    "total_orders": total_orders,
                    "new_customers": new_customers
                }
            })
        except Shop.DoesNotExist:
            return Response({"error": "No shop found"}, status=404)



@method_decorator(csrf_exempt, name='dispatch') # Add this for extra safety
class SellerUpdateOrderStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # 1. Fetch order and ensure ownership
        order = get_object_or_404(Order, pk=pk, shop__owner=request.user)

        # 2. Extract status from request (usually 'ready_for_pickup')
        new_status = request.data.get('status')
        
        # 3. Validation
        if not new_status:
            return Response({"error": "Status is required"}, status=400)

        # 4. Update and Save
        order.delivery_status = new_status
        order.save()

        # Yusuf: If status is 'ready_for_pickup', it will now show up for the Rider
        return Response({"message": f"Order #{pk} updated to {new_status}"})



# Rider views moved to logistics/views.py

class AdminDashboardStatsView(APIView):
    """
    SUPER ADMIN: Returns global system statistics.
    """
    permission_classes = [permissions.IsAdminUser] # Only for is_staff=True users

    def get(self, request):
        # 1. User Stats
        User = get_user_model()
        total_users = User.objects.count()
        total_sellers = Shop.objects.count()
        
        # 2. Financial Stats
        total_wallet_balance = Wallet.objects.aggregate(Sum('available_balance'))['available_balance__sum'] or 0.00
        
        # 3. Order Stats
        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(delivery_status='pending').count()
        completed_orders = Order.objects.filter(delivery_status='delivered').count()
        paid_orders = Order.objects.filter(payment_status='paid').count()
        
        # 4. Total Volume (Gross Merchandise Value)
        gmv = Order.objects.aggregate(Sum('total_price'))['total_price__sum'] or 0.00

        return Response({
            "users": {
                "total": total_users,
                "sellers": total_sellers
            },
            "finance": {
                "wallet_liability": total_wallet_balance,
                "gmv": gmv
            },
            "orders": {
                "total": total_orders,
                "pending": pending_orders,
                "completed": completed_orders,
                "paid": paid_orders
            }
        })


class AdminOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request):
        try:
            User = get_user_model()
            
            # 1. Broad User Demographics
            total_users = User.objects.count()
            admins_count = User.objects.filter(is_staff=True).count()
            
            # 🔥 Use 'active_role' instead of 'role' based on model metadata inspect
            sellers_count = User.objects.filter(active_role__iexact='seller').count()
            
            # Fallback check: If active_role isn't written out yet, cross-verify with existing shops
            if sellers_count == 0:
                sellers_count = Shop.objects.values('owner').distinct().count()
                
            buyers_count = total_users - sellers_count - admins_count
            if buyers_count < 0: 
                buyers_count = 0

            # 2. Marketplace Catalog Metrics
            total_shops = Shop.objects.count()
            total_products = Product.objects.count()

            # 3. Financial Ledger Aggregation (Safe fallback targeting 'payment_status' instead of missing 'is_paid')
            paid_orders = Order.objects.filter(payment_status__iexact='paid')
            if not paid_orders.exists():
                paid_orders = Order.objects.filter(payment_status__iexact='released')
                
            revenue_data = paid_orders.aggregate(Sum('total_price'))
            total_revenue = revenue_data['total_price__sum'] or 0

            # 4. Formulating List Objects Loops safely
            pending_shops = Shop.objects.filter(is_active=False).select_related('owner')
            shops_data = [{
                "id": str(shop.id),
                "name": shop.name,
                "shop_type": shop.shop_type,
                "id_type": getattr(shop, 'id_type', ''),
                "owner_email": shop.owner.email
            } for shop in pending_shops]

            users_data = [{
                "id": user.pk,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": getattr(user, 'active_role', 'buyer') or 'buyer',
                "is_staff": user.is_staff
            } for user in User.objects.all().order_by('-date_joined')[:50]] # Limit 50 for mobile optimization

            return Response({
                "metrics": {
                    "total_users": total_users,
                    "sellers": sellers_count,
                    "buyers": buyers_count,
                    "admins": admins_count,
                    "total_shops": total_shops,
                    "total_products": total_products,
                    "total_revenue": f"₦{total_revenue:,}"
                },
                "pending_shops": shops_data,
                "users": users_data
            }, status=200)

        except Exception as e:
            # Return exact error debug details to mobile console stream instead of blank zeroing
            return Response({"status": "error", "message": f"Crash details: {str(e)}"}, status=500)


class AdminApproveShopView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, shop_id):
        try:
            shop = Shop.objects.get(pk=shop_id)
            shop.is_active = True
            shop.save()
            return Response({"status": "success", "message": "Shop approved successfully"}, status=status.HTTP_200_OK)
        except Shop.DoesNotExist:
            return Response({"status": "error", "message": "Shop record not found"}, status=status.HTTP_404_NOT_FOUND)


class AdminReviewShopView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, shop_id):
        """
        Processes administrative approval or rejection flags for UUID shop models.
        """
        shop = get_object_or_404(Shop, id=shop_id)
        action = request.data.get('action') 

        if action == 'approve':
            shop.is_active = True
            shop.save()

            # Elevate user permission role
            owner = shop.owner
            owner.active_role = 'seller'
            owner.save()

            return Response({"status": "success", "message": f"'{shop.name}' has been successfully activated. Owner role elevated to Seller."}, status=200)

        elif action == 'reject':
            shop.delete() # Purge row registry sheet cleanly so they can fix mistakes
            return Response({"status": "success", "message": "Shop application record rejected and cleared safely."}, status=200)

        return Response({"status": "error", "message": "Invalid control modifier parameter."}, status=400)


# Chat views moved to chat/views.py

class ProductDeleteView(generics.DestroyAPIView):
    """
    Allows a vendor to delete their own product.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Isolation: Users can only see/delete products from their own shop
        return Product.objects.filter(shop__owner=self.request.user)



class ProductUpdateView(generics.RetrieveUpdateAPIView):
    """
    Allows a vendor to update their own product details or images.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Isolation: Vendors can only access and update products from their own shop
        return Product.objects.filter(shop__owner=self.request.user)


class SellerOrderDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrderSerializer
    # CHANGE THIS: Use JWT instead of TokenAuthentication
    authentication_classes = [JWTAuthentication] 
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # We ensure the vendor only sees orders from their own shop
        return Order.objects.filter(shop__owner=self.request.user)


class ShopListView(generics.ListAPIView):
    queryset = Shop.objects.filter(is_active=True).select_related('owner')
    serializer_class = ShopSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'shop_type', 'state']



class ShopDetailView(generics.RetrieveAPIView):
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    permission_classes = [AllowAny] # Anyone can visit a shop




@method_decorator(cache_page(300), name='dispatch')
@method_decorator(vary_on_headers('Authorization'), name='dispatch')
class ProductVideoFeedView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Product.objects.exclude(video="").exclude(video__isnull=True).select_related('shop', 'category').prefetch_related('images').order_by('-created_at')



class ActivateSellerAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # 1. Update Roles Silently
        if not user.roles:
            user.roles = []
            
        if 'seller' not in user.roles:
            user.roles.append('seller')
            # Important: Switch their active role to seller immediately
            user.active_role = 'seller'
            user.save()
            
        # 2. Create the Shop with a default name
        # Using get_or_create prevents errors if they click twice
        shop, created = Shop.objects.get_or_create(
            owner=user, 
            defaults={
                'name': f"{user.full_name or 'My'}'s Shop",
                'description': "Welcome to my shop! Updates coming soon."
            }
        )
        
        # 3. Return the shop info so the frontend can update its state
        return Response({
            "message": "Shop created successfully",
            "active_role": user.active_role,
            "shop_id": shop.id,
            "shop_name": shop.name
        })


class MarkOrderDispatchedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        try:
            # 1. Ensure the user is the owner of the shop that sold the item
            order = Order.objects.get(id=order_id, shop__owner=request.user)
            
            if order.delivery_status != 'pending':
                return Response({"error": f"Cannot dispatch order in '{order.delivery_status}' status."}, status=400)

            # 2. Update status to 'shipped'
            order.delivery_status = 'shipped'
            order.save()

            return Response({
                "message": "Order marked as dispatched. Buyer has been notified.",
                "status": order.delivery_status
            }, status=200)

        except Order.DoesNotExist:
            return Response({"error": "Order not found or you are not the seller."}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class AdminUpdateUserRoleView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser] # Robust security restriction

    def post(self, request, user_id):
        target_role = request.data.get('role')
        if target_role not in ['admin', 'seller', 'buyer']:
            return Response({"status": "error", "message": "Invalid targeted identity scope parameters."}, status=400)

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            if target_role == 'admin':
                user.is_staff = True
                user.is_superuser = True
                user.active_role = 'admin'
                if 'admin' not in user.roles:
                    user.roles.append('admin')
                if hasattr(user, 'role'):
                    user.role = 'admin'
            elif target_role == 'seller':
                user.is_staff = False
                user.is_superuser = False
                user.active_role = 'seller'
                if 'seller' not in user.roles:
                    user.roles.append('seller')
                if hasattr(user, 'role'):
                    user.role = 'seller'
            else:
                user.is_staff = False
                user.is_superuser = False
                user.active_role = 'buyer'
                if 'buyer' not in user.roles:
                    user.roles.append('buyer')
                if hasattr(user, 'role'):
                    user.role = 'buyer'
                
            user.save()
            return Response({"status": "success", "message": "User role permissions remapped completely."}, status=200)
        except User.DoesNotExist:
            return Response({"status": "error", "message": "Target account file reference missing."}, status=404)


class MerchantAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        shop = Shop.objects.filter(owner=user).first()

        if not shop:
            return Response({
                "status": "none",
                "message": "No store instance exists on file for this account record.",
                "shop_name": None,
                "stats": {
                    "total_sales": "₦0",
                    "total_orders": "0",
                    "products_sold": "0",
                    "new_customers": "0",
                    "top_products": []
                }
            }, status=status.HTTP_200_OK)

        if not shop.is_active:
            return Response({
                "status": "pending",
                "message": "Your registration file is currently awaiting administrator activation.",
                "shop_name": shop.name,
                "stats": {
                    "total_sales": "₦0",
                    "total_orders": "0",
                    "products_sold": "0",
                    "new_customers": "0",
                    "top_products": []
                }
            }, status=status.HTTP_200_OK)

        # Fetch all paid order items for this shop in one query
        paid_items = list(OrderItem.objects.filter(
            product__shop=shop,
            order__payment_status='paid'
        ).select_related('product', 'order'))

        # 1. Total Sales Revenue
        total_revenue = sum(item.quantity * item.product.price for item in paid_items)
        if total_revenue >= 100_000:
            formatted_sales = f"₦{int(total_revenue / 1000)}k"
        else:
            formatted_sales = f"₦{total_revenue:,.0f}"

        # 2. Total Orders Count
        unique_order_ids = {item.order_id for item in paid_items}
        total_orders_count = len(unique_order_ids)

        # 3. Products Sold Volume
        products_sold_volume = sum(item.quantity for item in paid_items)

        # 4. Unique Customers
        unique_customer_ids = {item.order.buyer_id for item in paid_items}
        unique_customers_count = len(unique_customer_ids)

        # 5. Top Products (computed in-memory to avoid N+1 queries)
        product_sales_map = defaultdict(int)
        for item in paid_items:
            product_sales_map[item.product_id] += item.quantity

        top_products = []
        for prod in Product.objects.filter(shop=shop):
            sales_count = product_sales_map.get(prod.id, 0)
            denominator = sales_count + prod.stock
            percentage = int((sales_count / denominator) * 100) if denominator > 0 else 0
            top_products.append({
                "name": prod.name,
                "sales_count": sales_count,
                "stock": prod.stock,
                "percentage": percentage,
            })

        top_products = sorted(top_products, key=lambda x: x['sales_count'], reverse=True)[:3]

        return Response({
            "status": "approved",
            "shop_name": shop.name,
            "stats": {
                "total_sales": formatted_sales,
                "total_orders": str(total_orders_count),
                "products_sold": str(products_sold_volume),
                "new_customers": str(unique_customers_count),
                "top_products": top_products,
            }
        }, status=status.HTTP_200_OK)


class MyShopStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Look up any shop row belonging to this authenticated user account
        shop = Shop.objects.filter(owner=user).first()
        
        if not shop:
            return Response({"status": "none", "message": "No shop record exists on file."})
            
        if not shop.is_active:
            return Response({"status": "pending", "message": "Application is pending administrator approval."})
            
        return Response({"status": "approved", "message": "Shop is fully active."})


class MerchantWithdrawalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _monnify_auth_token(self):
        url = settings.MONNIFY_BASE_URL.rstrip('/') + '/api/v1/auth/login'
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded = base64.b64encode(auth_str.encode()).decode()
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Basic {encoded}", "Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()['responseBody']['accessToken']
        except Exception as e:
            logger.error(f"Monnify auth failure: {e}")
        return None

    def post(self, request):
        amount = request.data.get('amount')
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        pin = request.data.get('transaction_pin')

        if not all([amount, bank_code, account_number, pin]):
            return Response(
                {"error": "Missing required fields: amount, bank_code, account_number, transaction_pin"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.transaction_pin:
            return Response({"error": "No transaction PIN set. Set one in your profile first."}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_transaction_pin(pin):
            return Response({"error": "Invalid transaction PIN."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            return Response({"error": "Invalid amount format."}, status=status.HTTP_400_BAD_REQUEST)

        if amount_dec <= 0:
            return Response({"error": "Amount must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

        token = self._monnify_auth_token()
        if not token:
            return Response(
                {"error": "Could not authenticate with payment processor. Try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        reference = f"WTH-{uuid_lib.uuid4().hex[:12]}-{int(timezone.now().timestamp())}"
        disbursement_url = settings.MONNIFY_BASE_URL.rstrip('/') + '/api/v2/disbursements/single'
        payload = {
            "amount": float(amount_dec),
            "reference": reference,
            "narration": "GLAPP Storefront Payout Fulfillment",
            "destinationBankCode": bank_code,
            "destinationAccountNumber": account_number,
            "currency": "NGN",
            "sourceAccountNumber": settings.MONNIFY_WALLET_ACCOUNT_NUMBER,
        }

        try:
            disburse_resp = requests.post(
                disbursement_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            result = disburse_resp.json()
        except requests.RequestException as e:
            logger.error(f"Monnify disbursement connection failure: {e}")
            return Response(
                {"error": "Could not reach payment processor. Try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not (result.get("requestSuccessful") and disburse_resp.status_code in (200, 201)):
            error_msg = result.get("responseMessage", "Payment processor rejected the request")
            return Response(
                {"error": f"Verification error: {error_msg}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)

            if wallet.available_balance < amount_dec:
                return Response(
                    {"error": "Insufficient available balance. Locked funds cannot be withdrawn."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            wallet.available_balance -= amount_dec
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=-amount_dec,
                transaction_type=Transaction.TransactionType.WITHDRAWAL,
                status=Transaction.Status.SUCCESS,
                reference=reference,
                description=f"Withdrawal to {account_number}",
            )

        return Response(
            {
                "message": "Withdrawal processed successfully.",
                "reference": reference,
            },
            status=status.HTTP_200_OK,
        )
