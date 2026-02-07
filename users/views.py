from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, RegistrationSerializer, KYCUploadSerializer, AdminKYCSerializer
from django.shortcuts import get_object_or_404

from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import KYCUploadSerializer

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegistrationSerializer

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get or Update own profile (e.g., change name, phone).
    """
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class AddRoleView(APIView):
    """
    Allows a user to activate a new role (e.g., "Become a Seller").
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        role_to_add = request.data.get('role')
        if role_to_add not in User.Roles.values:
            return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        if role_to_add not in user.roles:
            user.roles.append(role_to_add)
            user.save()
            
        return Response({"message": f"Role {role_to_add} added successfully", "roles": user.roles})

class KYCSubmissionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        user = request.user
        if user.kyc_status == 'verified':
            return Response({"message": "Already verified"}, status=200)

        # Update document details
        serializer = KYCUploadSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Set status to pending for Admin review
            user.kyc_status = 'pending'
            user.save()
            return Response({
                "status": "pending",
                "message": "Documents uploaded. Waiting for admin approval."
            }, status=200)
        
        return Response(serializer.errors, status=400)


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
        
        # 2. Financial Stats (Escrow)
        # Calculate total money currently held in all user wallets (Liability)
        total_wallet_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0.00
        total_escrow_locked = Wallet.objects.aggregate(Sum('escrow_balance'))['escrow_balance__sum'] or 0.00
        
        # 3. Order Stats
        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(delivery_status='pending').count()
        completed_orders = Order.objects.filter(delivery_status='delivered').count()
        
        # 4. Total Volume (Gross Merchandise Value)
        gmv = Order.objects.aggregate(Sum('total_price'))['total_price__sum'] or 0.00

        return Response({
            "users": {
                "total": total_users,
                "sellers": total_sellers
            },
            "finance": {
                "wallet_liability": total_wallet_balance,
                "escrow_locked": total_escrow_locked,
                "gmv": gmv
            },
            "orders": {
                "total": total_orders,
                "pending": pending_orders,
                "completed": completed_orders
            }
        })




class AdminKYCListView(generics.ListAPIView):
    """
    ADMIN: List all users waiting for verification.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminKYCSerializer

    def get_queryset(self):
        return User.objects.filter(kyc_status='pending')

class AdminKYCActionView(APIView):
    """
    Next.js will call this: POST /api/users/admin/kyc/<id>/action/
    Body: {"action": "approve"} or {"action": "reject", "reason": "ID is blurry"}
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        user_to_verify = get_object_or_404(User, pk=pk)
        action = request.data.get('action')
        reason = request.data.get('reason', '')

        if action == 'approve':
            user_to_verify.kyc_status = User.KycStatus.VERIFIED
            user_to_verify.rejection_reason = None # Clear any old errors
            user_to_verify.save()
            return Response({"message": f"User {user_to_verify.email} verified successfully."})

        elif action == 'reject':
            user_to_verify.kyc_status = User.KycStatus.REJECTED
            user_to_verify.rejection_reason = reason
            user_to_verify.save()
            return Response({"message": "KYC rejected. User notified of the reason."})

        return Response({"error": "Invalid action. Use 'approve' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)