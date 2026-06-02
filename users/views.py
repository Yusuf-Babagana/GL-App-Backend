from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, RegistrationSerializer, KYCUploadSerializer, AdminKYCSerializer
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import KYCUploadSerializer

User = get_user_model()

class CustomRegisterView(APIView):
    permission_classes = [permissions.AllowAny] # Allow anyone to register an account

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')

        # 1. Structural Validation Checklist
        print(f"📥 REGISTRATION INCOMING: email={email!r}, password={'***' if password else None}, first_name={first_name!r}, last_name={last_name!r}")

        if not email or not password:
            print(f"❌ REGISTRATION FAIL: missing fields — email={email!r}, password={'***' if password else None}")
            return Response({"status": "error", "message": "Email and password are required fields."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            print(f"❌ REGISTRATION FAIL: duplicate email={email!r}")
            return Response({"status": "error", "message": "An account with this email address already exists."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 2. Build the Model Row Entry
            full_name = f"{first_name} {last_name}".strip() or "Globalink User"
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                active_role='buyer',
                roles=['buyer']
            )

            # 3. Generate instant login tokens so the user skips logging in right after registering
            refresh = RefreshToken.for_user(user)
            
            # Send a uniform, predictable object dictionary
            payload = {
                "status": "success",
                "token": str(refresh.access_token),
                "user": {
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_admin": False,
                    "role": "buyer"
                }
            }
            print(f"📡 REGISTRATION SUCCESS OUTGOING: {payload}")
            return Response(payload, status=status.HTTP_201_CREATED) # 🌟 Explicit 201 Created Status Code

        except Exception as e:
            print(f"❌ REGISTRATION INTERNAL CRASH: {str(e)}")
            return Response({"status": "error", "message": f"Server processing failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        # total_sellers = Store.objects.count()
        
        # 2. Financial Stats (Escrow)
        # Calculate total money currently held in all user wallets (Liability)
        # total_wallet_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0.00
        # total_escrow_locked = Wallet.objects.aggregate(Sum('escrow_balance'))['escrow_balance__sum'] or 0.00
        
        # 3. Order Stats
        # total_orders = Order.objects.count()
        # pending_orders = Order.objects.filter(delivery_status='pending').count()
        # completed_orders = Order.objects.filter(delivery_status='delivered').count()
        
        # 4. Total Volume (Gross Merchandise Value)
        # gmv = Order.objects.aggregate(Sum('total_price'))['total_price__sum'] or 0.00

        return Response({
            "users": {
                "total": total_users,
                # "sellers": total_sellers
            },
            "finance": {
                # "wallet_liability": total_wallet_balance,
                # "escrow_locked": total_escrow_locked,
                # "gmv": gmv
            },
            "orders": {
                # "total": total_orders,
                # "pending": pending_orders,
                # "completed": completed_orders
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

class SetTransactionPINView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        pin = request.data.get('pin')
        old_pin = request.data.get('old_pin')
        
        if not pin or len(str(pin)) != 4:
            return Response({"error": "PIN must be 4 digits."}, status=400)

        user = request.user

        # FIX: Check if PIN is not None AND not an empty string
        if user.transaction_pin and user.transaction_pin.strip() != "":
            if not old_pin:
                return Response({"error": "Old PIN required to set a new one."}, status=400)
            if not user.check_transaction_pin(old_pin):
                return Response({"error": "Incorrect Old PIN."}, status=400)

        user.set_transaction_pin(pin)
        user.save()
        return Response({"message": "Transaction PIN updated successfully."}, status=200)

class UpdateBVNView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        bvn = request.data.get('bvn')
        print("DEBUG: BVN received:", bvn)

        if not bvn or len(str(bvn)) != 11:
            print("DEBUG: BVN validation failed - not 11 digits")
            return Response({"error": "A valid 11-digit BVN is required"}, status=400)

        user = request.user
        user.bvn = str(bvn).strip()
        user.save()
        print("DEBUG: BVN saved for user:", user.id)

        from finance.utils import MonnifyAPI
        acc_data, error_msg = MonnifyAPI.create_virtual_account(user)

        if acc_data:
            wallet = user.wallet
            wallet.account_number = acc_data['account_number']
            wallet.bank_name = acc_data['bank_name']
            wallet.bank_code = acc_data['bank_code']
            wallet.save()
            print("DEBUG: Virtual account created:", acc_data['account_number'])
            return Response({"message": "Success", "account": acc_data}, status=200)

        print("DEBUG: Virtual account creation failed:", error_msg)
        return Response({"error": error_msg or "Virtual account creation failed"}, status=400)


class RequestAccountDeletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.is_deactivation_pending:
            return Response({
                "message": "Deletion already requested. Use /cancel-deletion/ to reverse it."
            }, status=400)

        from django.utils import timezone
        user.is_deactivation_pending = True
        user.deletion_requested_at = timezone.now()
        user.save()

        from .utils import send_deletion_requested_email
        send_deletion_requested_email(user)

        return Response({
            "message": "Account deletion requested. A confirmation email has been sent.",
            "deletion_requested_at": user.deletion_requested_at,
        }, status=200)


class CancelAccountDeletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        if not user.is_deactivation_pending:
            return Response({
                "message": "No pending deletion request."
            }, status=400)

        user.is_deactivation_pending = False
        user.deletion_requested_at = None
        user.save()

        from .utils import send_deletion_cancelled_email
        send_deletion_cancelled_email(user)

        return Response({
            "message": "Account deletion request cancelled."
        }, status=200)


class CustomLoginView(APIView):
    permission_classes = [permissions.AllowAny] # Allow public access to log in

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        print(f"📥 LOGIN INCOMING: email={email!r}, password={'***' if password else None}")

        # Django's ModelBackend expects the identifier in the 'username' keyword argument
        # even when USERNAME_FIELD is 'email'. We check both to be completely bulletproof.
        user = authenticate(username=email, password=password)
        if user is None:
            user = authenticate(email=email, password=password)

        if user is None:
            reason = "inactive" if User.objects.filter(email=email, is_active=False).exists() else "invalid credentials or nonexistent email"
            print(f"❌ LOGIN FAIL: {reason} — email={email!r}")

        if user is not None:
            refresh = RefreshToken.for_user(user)
            token_string = str(refresh.access_token)
            
            # Determine role safely with explicit overrides for admin/staff members
            user_role = getattr(user, 'active_role', 'buyer') or 'buyer'
            if user.is_staff or user.is_superuser:
                user_role = 'admin' # Force alignment over default model fallbacks
            
            payload = {
                "token": token_string,  # 💥 EXACT MATCH FOR FRONTEND
                "refresh": str(refresh),
                "user": {
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_admin": user.is_staff or user.is_superuser,
                    "role": user_role  # 💥 Guaranteed to return 'admin' for admins now
                }
            }
            print(f"📡 DEBUG Server outgoing login payload: {payload}")
            return Response(payload, status=status.HTTP_200_OK)
            
        return Response({"error": "Invalid email or password credentials"}, status=status.HTTP_401_UNAUTHORIZED)