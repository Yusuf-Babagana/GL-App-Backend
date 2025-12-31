from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
# --- ADDED THESE MISSING IMPORTS ---
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import serializers 
# -----------------------------------
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Category, Store, Product, Order, Cart, CartItem
from .serializers import (
    CategorySerializer, StoreSerializer, ProductSerializer, 
    OrderSerializer, CartSerializer
)

class StoreCreateView(generics.CreateAPIView):
    """ Allows a user to create their own store """
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # For logo upload

    def perform_create(self, serializer):
        # Assign the logged-in user as the owner
        serializer.save(owner=self.request.user)
        
        # Auto-update user role to 'seller'
        # Check if roles is a list (JSONField) or needs initialization
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
        # Filter products where the store owner is the current user
        return Product.objects.filter(store__owner=self.request.user).order_by('-created_at')

class ProductCreateView(generics.CreateAPIView):
    """ Allows a seller to add a new product """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        # Get the user's store
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
    """
    Public product search with filtering.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'category__name']

class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

# --- SELLER DASHBOARD (Alternative Implementation - kept as requested) ---

class CreateStoreView(generics.CreateAPIView):
    """
    Allows a user to open their store.
    """
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # Link store to current user
        serializer.save(owner=self.request.user)

class SellerProductListCreateView(generics.ListCreateAPIView):
    """
    GET: List only MY store's products.
    POST: Add a new product to MY store.
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Ensure user has a store
        if not hasattr(self.request.user, 'store'):
            return Product.objects.none()
        return Product.objects.filter(store=self.request.user.store)

    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'store'):
            raise permissions.PermissionDenied("You must open a store first.")
        serializer.save(store=self.request.user.store)

# --- BUYER ACTIONS ---

class CreateOrderView(APIView):
    """
    Simple checkout logic: Converts Cart -> Order.
    Real logic would involve payment gateways here.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # 1. Get User Cart (Simplified)
        # In a real scenario, we'd fetch items from the Cart model
        # For now, we accept a list of {product_id, quantity} in body
        
        items_data = request.data.get('items', [])
        if not items_data:
            return Response({"error": "No items provided"}, status=400)

        # Logic to group items by Store (since orders are per store)
        # This is complex, so we'll do a simplified single-order version for MVP
        
        return Response({"message": "Order created successfully (Mock)"})