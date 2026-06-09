from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import User
from finance.models import Wallet, Transaction
from finance.serializers import TransactionSerializer as FinanceTransactionSerializer
from market.models import Order, Shop
from market.serializers import OrderSerializer as MarketOrderSerializer

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


# --- ORDER MANAGEMENT (Admin Dashboard) ---

class AdminOrderManageSerializer(serializers.ModelSerializer):
    buyer_email = serializers.EmailField(source='buyer.email', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'buyer_email', 'buyer_name', 'shop_name',
            'total_price', 'delivery_status', 'payment_status',
            'items_count', 'created_at', 'updated_at',
        ]

    def get_items_count(self, obj):
        try:
            return obj.items.count()
        except Exception:
            return 0


class AdminOrderListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminOrderManageSerializer

    def get_queryset(self):
        qs = Order.objects.select_related('buyer', 'shop').order_by('-created_at')
        search = self.request.query_params.get('search', '').strip()
        status_filter = self.request.query_params.get('status', '').strip()
        payment = self.request.query_params.get('payment', '').strip()
        if search:
            qs = qs.filter(
                Q(buyer__email__icontains=search) |
                Q(buyer__full_name__icontains=search) |
                Q(shop__name__icontains=search) |
                Q(id__icontains=search)
            )
        if status_filter:
            qs = qs.filter(delivery_status=status_filter)
        if payment:
            qs = qs.filter(payment_status=payment)
        return qs


# --- TRANSACTION MONITOR (Admin Dashboard) ---

class AdminTransactionSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='wallet.user.email', read_only=True)
    user_name = serializers.CharField(source='wallet.user.full_name', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'user_email', 'user_name', 'amount',
            'transaction_type', 'status', 'description',
            'reference', 'related_order_id', 'created_at',
        ]


class AdminTransactionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminTransactionSerializer

    def get_queryset(self):
        qs = Transaction.objects.select_related('wallet__user').order_by('-created_at')
        ttype = self.request.query_params.get('type', '').strip()
        status_filter = self.request.query_params.get('status', '').strip()
        search = self.request.query_params.get('search', '').strip()
        days = self.request.query_params.get('days', '').strip()
        if ttype:
            qs = qs.filter(transaction_type=ttype)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(
                Q(wallet__user__email__icontains=search) |
                Q(wallet__user__full_name__icontains=search) |
                Q(reference__icontains=search) |
                Q(description__icontains=search)
            )
        if days:
            try:
                cutoff = timezone.now() - timedelta(days=int(days))
                qs = qs.filter(created_at__gte=cutoff)
            except ValueError:
                pass
        return qs


# --- USER MANAGEMENT (Admin Dashboard) ---

class AdminUserManageSerializer(serializers.ModelSerializer):
    kyc_status_display = serializers.CharField(source='get_kyc_status_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone_number',
            'active_role', 'roles', 'kyc_status', 'kyc_status_display',
            'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_seen',
        ]


class AdminUserManageListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUserManageSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by('-date_joined')
        search = self.request.query_params.get('search', '').strip()
        role = self.request.query_params.get('role', '').strip()
        status_filter = self.request.query_params.get('status', '').strip()
        kyc = self.request.query_params.get('kyc', '').strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search)
            )
        if role:
            qs = qs.filter(active_role=role)
        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)
        if kyc:
            qs = qs.filter(kyc_status=kyc)
        return qs


class AdminUserToggleActiveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.is_active = not user.is_active
            user.save()
            return Response({
                'status': 'success',
                'is_active': user.is_active,
                'message': f'{user.email} {"activated" if user.is_active else "deactivated"}.'
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)


class AdminUserChangeRoleView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, user_id):
        role = request.data.get('role', '').strip()
        valid_roles = ['buyer', 'seller', 'job_seeker', 'employer', 'delivery_partner', 'admin']
        if role not in valid_roles:
            return Response({'error': f'Invalid role. Valid: {", ".join(valid_roles)}'}, status=400)
        try:
            user = User.objects.get(id=user_id)
            if role not in user.roles:
                user.roles.append(role)
            user.active_role = role
            user.save()
            return Response({
                'status': 'success',
                'active_role': user.active_role,
                'message': f'{user.email} role set to {role}.'
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)


# --- CHART DATA (Admin Dashboard) ---

class AdminChartDataView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        today = timezone.now()
        days = int(request.query_params.get('days', 7))
        cutoff = today - timedelta(days=days)
        date_range = [(today - timedelta(days=i)).date() for i in range(days - 1, -1, -1)]

        # Revenue per day (successful payment & deposit transactions)
        revenue_qs = Transaction.objects.filter(
            created_at__gte=cutoff,
            status='success',
            transaction_type__in=['payment', 'deposit']
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            total=Sum('amount')
        ).order_by('date')
        revenue_map = {r['date']: float(r['total']) for r in revenue_qs}
        revenue_data = [round(revenue_map.get(d, 0), 2) for d in date_range]

        # Orders per day
        orders_qs = Order.objects.filter(
            created_at__gte=cutoff
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        orders_map = {r['date']: r['count'] for r in orders_qs}
        orders_data = [orders_map.get(d, 0) for d in date_range]

        # New users per day
        users_qs = User.objects.filter(
            date_joined__gte=cutoff
        ).annotate(
            date=TruncDate('date_joined')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        users_map = {r['date']: r['count'] for r in users_qs}
        users_data = [users_map.get(d, 0) for d in date_range]

        labels = [d.strftime('%b %d') for d in date_range]

        return Response({
            'labels': labels,
            'revenue': revenue_data,
            'orders': orders_data,
            'users': users_data,
        })