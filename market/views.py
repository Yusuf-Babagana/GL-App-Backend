from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.db import transaction, models
from django.db.models import Q
from rest_framework import generics, permissions, status, filters, views
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers 
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
# Local Imports
from .models import Category, Store, Product, Order, OrderItem, Cart, CartItem, ProductImage
from .serializers import (
    CategorySerializer, StoreSerializer, ProductSerializer, 
    OrderSerializer, CartSerializer
)
from finance.models import Wallet, Transaction
from .models import Conversation, Message
import requests
from django.db.models import Max
from finance.services import WalletService
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from rest_framework.permissions import AllowAny # Professional: Let visitors see stores


# --- SELLER / STORE VIEWS ---

class StoreCreateView(generics.CreateAPIView):
    """ Allows a user to create their own store """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    # --- DEBUGGING FIX: Override POST to see errors ---
    def post(self, request, *args, **kwargs):
        print("Received Store Data:", request.data) # <--- Debug Print
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

class SellerProductListView(generics.ListAPIView):
    """ Lists only products belonging to the logged-in seller """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(store__owner=self.request.user).order_by('-created_at')

# Find the ProductCreateView and update the parser_classes
@method_decorator(csrf_exempt, name='dispatch')
class ProductCreateView(generics.CreateAPIView):
    """ Allows a seller to add a new product via JSON or Multipart """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    # ADDED JSONParser here to fix the 415 error
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        print("Received Product Data:", request.data)
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print("Product Validation Errors:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        try:
            # 1. Grab metadata from request
            video_url = self.request.data.get('video_url')
            image_links = self.request.data.get('images', [])
            
            # 2. Get the user's store
            store = Store.objects.get(owner=self.request.user)
            
            # 3. Save the product (Automation: ensure is_ad is True)
            if video_url:
                product = serializer.save(store=store, video=video_url, is_ad=True)
            else:
                product = serializer.save(store=store, is_ad=True)

            # 4. Automatic "Image Creation": Save the list of links to the database
            if isinstance(image_links, list):
                for i, link in enumerate(image_links):
                    ProductImage.objects.create(
                        product=product,
                        image=link,
                        is_primary=(i == 0) # Set first as primary
                    )
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

# --- SELLER DASHBOARD ---

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


# --- 2. UPDATE THE CLASS LIKE THIS ---
# At the top with your other imports
from finance.utils import WalletManager
from finance.services import WalletService

@method_decorator(csrf_exempt, name='dispatch')
class CreateOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        print(f"\n--- 🛒 DIRECT SETTLEMENT CHECKOUT: {request.user.email} ---")
        try:
            cart = Cart.objects.get(user=request.user)
            if not cart.items.exists():
                return Response({"error": "Cart is empty"}, status=400)

            cart_total = Decimal(str(cart.total_price))
            seller = cart.items.first().product.store.owner

            if seller == request.user:
                return Response({"error": "You cannot buy from your own store."}, status=400)

            # 1. Direct Settlement to Seller's PENDING balance
            success, message = WalletManager.settle_to_pending(
                buyer=request.user,
                amount=cart_total,
                seller=seller
            )

            if not success:
                return Response({"error": message}, status=400)

            # 2. Create the Order (Marked as Released because buyer has already paid)
            with transaction.atomic():
                order = Order.objects.create(
                    buyer=request.user,
                    store=cart.items.first().product.store,
                    total_price=cart_total,
                    shipping_address_json=request.data.get('shipping_address', {}),
                    payment_status=Order.PaymentStatus.RELEASED, 
                    delivery_status=Order.DeliveryStatus.PENDING,
                )
                
                # Transfer items from Cart to OrderItems
                items = [OrderItem(order=order, product=i.product, quantity=i.quantity, price_at_purchase=i.product.price) for i in cart.items.all()]
                OrderItem.objects.bulk_create(items)
                cart.items.all().delete()
                
            print(f"✅ SUCCESS: Order #{order.id} settled to Seller Pending.")
            return Response({"message": "Order placed!", "order_id": order.id}, status=201)

        except Exception as e:
            print(f"🔥 ERROR: {str(e)}")
            return Response({"error": str(e)}, status=400)

            
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
    Buyer confirms they received the item.
    This triggers the release of funds from Seller's pending_balance → available balance.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        print(f"--- 🏁 CONFIRMING RECEIPT FOR ORDER #{order_id} ---")
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id, buyer=request.user)

                if order.delivery_status == Order.DeliveryStatus.DELIVERED:
                    return Response({"error": "This order is already marked as delivered."}, status=400)

                # Release funds: Seller pending_balance → available balance
                success, message = WalletManager.finalize_settlement(order)
                if not success:
                    print(f"❌ ERROR: Could not release funds: {message}")
                    return Response({"error": message}, status=400)

                # Update statuses
                order.delivery_status = Order.DeliveryStatus.DELIVERED
                order.payment_status = Order.PaymentStatus.RELEASED
                order.save()

                print(f"✅ SUCCESS: Funds released to {order.store.owner.email}. Order #{order.id} complete.")
                return Response({"message": "Receipt confirmed! The seller has been paid. 🎉"})

        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=404)
        except Exception as e:
            print(f"🔥 CRITICAL ERROR: {str(e)}")
            return Response({"error": str(e)}, status=400)


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



@method_decorator(csrf_exempt, name='dispatch') # Add this for extra safety
class SellerUpdateOrderStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # 1. Fetch order and ensure ownership
        order = get_object_or_404(Order, pk=pk, store__owner=request.user)

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



class AvailableDeliveriesView(generics.ListAPIView):
    """
    RIDER: List orders that are 'ready_for_pickup' and have NO rider assigned yet.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 1. Status must be EXACTLY 'ready_for_pickup'
        # 2. Rider must be NULL (no one has taken it yet)
        return Order.objects.filter(
            delivery_status='ready_for_pickup', 
            rider__isnull=True
        ).order_by('-created_at')

class RiderMyDeliveriesView(generics.ListAPIView):
    """
    RIDER: List orders assigned to the logged-in rider.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(rider=self.request.user).order_by('-created_at')

class AcceptDeliveryView(APIView):
    """
    RIDER: Accept a job.
    """
    # CRITICAL: These two lines bypass the CSRF check for mobile JWT tokens
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # 1. Fetch the order
        order = get_object_or_404(Order, pk=pk)

        # 2. Safety Checks
        if order.rider is not None:
            return Response({"error": "This order has already been taken by another rider."}, status=status.HTTP_400_BAD_REQUEST)
        
        if order.delivery_status != 'ready_for_pickup':
            return Response({"error": "Order is not ready for pickup yet."}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Assign Rider and Fee
        with transaction.atomic():
            order.rider = request.user
            order.delivery_fee = Decimal('1500.00') # Fixed fee for MVP
            order.save()

            # 4. Ensure User has Rider role
            if not request.user.roles:
                request.user.roles = []
            if 'rider' not in request.user.roles:
                request.user.roles.append('rider')
                request.user.save()

        return Response({"message": "Job accepted! Head to the store for pickup."}, status=status.HTTP_200_OK)

class RiderUpdateStatusView(APIView):
    """
    Rider updates delivery status. Since payment is settled at checkout,
    delivery confirmation only updates the order status.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, rider=request.user)
        new_status = request.data.get('status')
        provided_pin = request.data.get('pin')

        if new_status == 'picked_up':
            order.delivery_status = 'picked_up'
            order.save()
            return Response({"message": "Picked up successfully"})

        elif new_status == 'delivered':
            if not provided_pin:
                return Response({"error": "PIN is missing"}, status=400)

            if str(provided_pin).strip() != str(order.delivery_code).strip():
                return Response({"error": "Incorrect PIN"}, status=400)

            # Payment already settled at checkout — just update delivery status
            order.delivery_status = Order.DeliveryStatus.DELIVERED
            order.save()

            print(f"✅ Rider confirmed delivery for Order #{order.id}")
            return Response({"message": "Delivery confirmed successfully!"})

        return Response({"error": "Invalid status"}, status=400)

class AdminDashboardStatsView(APIView):
    """
    SUPER ADMIN: Returns global system statistics.
    """
    permission_classes = [permissions.IsAdminUser] # Only for is_staff=True users

    def get(self, request):
        # 1. User Stats
        User = get_user_model()
        total_users = User.objects.count()
        total_sellers = Store.objects.count()
        
        # 2. Financial Stats
        total_wallet_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0.00
        
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


class StartChatView(APIView):
    """
    Get or Create a conversation between the logged-in user and a Seller (userId).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, userId):
        other_user = get_object_or_404(get_user_model(), pk=userId)
        
        # --- FIX: LOOKUP STORE NAME ---
        # 1. Check if the 'other_user' owns a store
        store = Store.objects.filter(owner=other_user).first()
        
        if store:
            partner_name = store.name  # Use Store Name (e.g. "Samsung")
        else:
            partner_name = other_user.full_name or "User" # Fallback

        # --- FIX: CHECK IF CONVERSATION EXISTS ---
        conversations = Conversation.objects.filter(participants=request.user).filter(participants=other_user)
        
        if conversations.exists():
            conversation = conversations.first()
        else:
            conversation = Conversation.objects.create()
            conversation.participants.add(request.user, other_user)
        
        # Return conversation details + messages
        messages = conversation.messages.order_by('created_at').values(
            'id', 'text', 'sender__id', 'sender__email', 'created_at'
        )
        
        return Response({
            "conversation_id": conversation.id,
            "partner_name": partner_name, # <--- SENDING CORRECT NAME NOW
            "messages": list(messages),

        }, status=status.HTTP_200_OK)

class SendMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversationId):
        conversation = get_object_or_404(Conversation, pk=conversationId)
        
        # ... (Security checks and Message creation code from before) ...
        text = request.data.get('text')
        message = Message.objects.create(conversation=conversation, sender=request.user, text=text)

        # --- NOTIFICATION LOGIC ---
        # 1. Find the "Other" person in the chat
        recipient = conversation.participants.exclude(id=request.user.id).first()

        # 2. If they have a token, send the alert
        if recipient and recipient.push_token:
            try:
                requests.post(
                    'https://exp.host/--/api/v2/push/send',
                    json={
                        'to': recipient.push_token,
                        'title': request.user.full_name or "New Message",
                        'body': text,
                        'sound': 'default',
                        'data': {'conversationId': conversation.id}, # Optional data
                    }
                )
            except Exception as e:
                print("Push Error:", e)

        
        return Response({
            "id": message.id,
            "text": message.text,
            "sender_id": message.sender.id,
            "created_at": message.created_at
        }, status=status.HTTP_201_CREATED)



class ConversationListView(generics.ListAPIView):
    """
    Lists all conversations for the logged-in user (Seller or Buyer).
    Shows the name of the *other* person in the chat.
    """
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # 1. Get all chats where I am a participant
        chats = Conversation.objects.filter(participants=request.user).annotate(
            last_msg_time=Max('messages__created_at')
        ).order_by('-last_msg_time')

        data = []
        for chat in chats:
            # 2. Find the "Other" person
            other_user = chat.participants.exclude(id=request.user.id).first()
            if not other_user: continue

            # 3. Determine Name (If they are a store, show Store Name. If user, show User Name)
            # Logic: If I am a Seller, 'other_user' is a Buyer (show Name).
            # If I am a Buyer, 'other_user' is a Seller (show Store Name).
            
            store = Store.objects.filter(owner=other_user).first()
            if store:
                name = store.name
                image = store.logo.url if store.logo else None
            else:
                name = other_user.full_name or "User"
                image = None
            
            # 4. Get last message preview
            last_msg_obj = chat.messages.last()
            preview = last_msg_obj.text if last_msg_obj else "New conversation"
            
            data.append({
                "id": chat.id,
                "other_user_id": other_user.id, # <--- CRITICAL for navigation
                "name": name,
                "image": image,
                "last_message": preview,
                "timestamp": last_msg_obj.created_at if last_msg_obj else chat.created_at
            })
            
        return Response(data)



# market/views.py

class ProductDeleteView(generics.DestroyAPIView):
    """
    Allows a vendor to delete their own product.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Isolation: Users can only see/delete products from their own store
        return Product.objects.filter(store__owner=self.request.user)



class ProductUpdateView(generics.RetrieveUpdateAPIView):
    """
    Allows a vendor to update their own product details or images.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Isolation: Vendors can only access and update products from their own store
        return Product.objects.filter(store__owner=self.request.user)


class SellerOrderDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrderSerializer
    # CHANGE THIS: Use JWT instead of TokenAuthentication
    authentication_classes = [JWTAuthentication] 
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # We ensure the vendor only sees orders from their own store
        return Order.objects.filter(store__owner=self.request.user)


class StoreListView(generics.ListAPIView):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    permission_classes = [AllowAny] # This allows visitors to browse the directory



class StoreDetailView(generics.RetrieveAPIView):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    permission_classes = [AllowAny] # Anyone can visit a store




class ProductVideoFeedView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # AUTOMATION: This query finds any product with a video, 
        # local or Cloudinary, and puts the newest ones first.
        return Product.objects.exclude(video="").exclude(video__isnull=True).order_by('-created_at')



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
            
        # 2. Create the Store with a default name
        # Using get_or_create prevents errors if they click twice
        store, created = Store.objects.get_or_create(
            owner=user, 
            defaults={
                'name': f"{user.full_name or 'My'}'s Store",
                'description': "Welcome to my store! Updates coming soon."
            }
        )
        
        # 3. Return the store info so the frontend can update its state
        return Response({
            "message": "Store created successfully",
            "active_role": user.active_role,
            "store_id": store.id,
            "store_name": store.name
        })


class MarkOrderDispatchedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        try:
            # 1. Ensure the user is the owner of the store that sold the item
            order = Order.objects.get(id=order_id, store__owner=request.user)
            
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
