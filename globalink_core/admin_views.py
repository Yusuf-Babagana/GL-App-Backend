from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from django.db.models import Sum
from users.models import User
from finance.models import Wallet, Transaction
from market.models import Order, Shop

# --- KYC & USER MANAGEMENT ---

class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone_number',
            'active_role', 'roles', 'kyc_status',
            'is_staff', 'is_superuser', 'is_active',
            'date_joined', 'last_seen'
        ]

class AdminUserListView(generics.ListAPIView):
    """Next.js will use this to show all users and their status"""
    queryset = User.objects.all().order_by('-date_joined')
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUserSerializer

class AdminVerifySellerView(APIView):
    """Next.js will call this when admin clicks 'Approve' on a seller"""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.is_verified = True # Assuming you have this field
            user.save()
            return Response({"message": f"Seller {user.email} verified successfully"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

# --- FINANCIAL CONTROL ---

class AdminTransactionMonitorView(generics.ListAPIView):
    """Monitor every single Naira moving in the system (Monnify + Escrow)"""
    queryset = Transaction.objects.all().order_by('-created_at')
    permission_classes = [permissions.IsAdminUser]

class AdminSystemStatsView(APIView):
    """The 'Big Picture' for the Next.js Dashboard Home"""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        total_users = User.objects.count()
        total_escrow = Wallet.objects.aggregate(sum=Sum('escrow_balance'))['sum'] or 0
        total_orders = Order.objects.count()
        
        return Response({
            "users": total_users,
            "money_in_escrow": total_escrow,
            "total_transactions": total_orders,
            "active_shops": Shop.objects.filter(is_active=True).count()
        })