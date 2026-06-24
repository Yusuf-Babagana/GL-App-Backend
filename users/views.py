import logging
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .serializers import UserSerializer, RegistrationSerializer, KYCUploadSerializer, AdminKYCSerializer
from django.shortcuts import get_object_or_404
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken

from finance.models import Wallet
from market.models import Order

logger = logging.getLogger(__name__)
User = get_user_model()

@method_decorator(csrf_exempt, name='dispatch')
class CustomRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')

        # Log the raw request info for debugging
        logger.warning(
            "REGISTER request — content_type=%s, keys=%s, email=%r, has_password=%s",
            request.content_type,
            list(request.data.keys()) if hasattr(request.data, 'keys') else 'N/A',
            email,
            'yes' if password else 'no',
        )

        if not email or not password:
            logger.error("REGISTER 400: missing email=%r or password=%s", email, 'SET' if password else 'UNSET')
            return Response({"status": "error", "message": "Email and password are required fields."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            logger.error("REGISTER 400: duplicate email=%r", email)
            return Response({"status": "error", "message": "This email is already taken."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            full_name = f"{first_name} {last_name}".strip() or "Globalink User"
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                active_role='buyer',
                roles=['buyer'],
                kyc_status=User.KycStatus.UNVERIFIED,
            )

            login(request, user)

            refresh = RefreshToken.for_user(user)

            payload = {
                "status": "success",
                "token": str(refresh.access_token),
                "user": {
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_admin": False,
                    "role": "buyer",
                },
            }
            logger.info("REGISTER 201: email=%r", email)
            return Response(payload, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("REGISTER 500: %s", e)
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
        total_sellers = User.objects.filter(active_role='seller').count()
        
        # 2. Financial Stats (Escrow)
        total_wallet_balance = Wallet.objects.aggregate(Sum('available_balance'))['available_balance__sum'] or 0.00
        total_escrow_locked = Wallet.objects.aggregate(Sum('locked_balance'))['locked_balance__sum'] or 0.00
        
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
        return User.objects.filter(kyc_status__in=['unverified', 'pending']).order_by('-date_joined')

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
        logger.info("UpdateBVN: BVN received for user %s", request.user.id)

        if not bvn or len(str(bvn)) != 11:
            logger.warning("UpdateBVN: validation failed — not 11 digits: %r", bvn)
            return Response({"error": "A valid 11-digit BVN is required"}, status=400)

        user = request.user
        user.bvn = str(bvn).strip()

        # Set thread-local flag so the post_save signal knows not to race
        # with us on Monnify account creation.
        from finance.signals import _thread_local
        _thread_local.skip_monnify = True
        try:
            user.save(update_fields=['bvn'])
        finally:
            _thread_local.skip_monnify = False

        # Refresh wallet from DB.
        wallet = user.wallet
        wallet.refresh_from_db()

        if wallet.account_number:
            logger.info("UpdateBVN: account already provisioned")
            return Response({
                "message": "Success",
                "account": {
                    "account_number": wallet.account_number,
                    "bank_name": wallet.bank_name,
                    "bank_code": wallet.bank_code,
                },
            }, status=200)

        from finance.utils import MonnifyAPI
        acc_data, error_msg = MonnifyAPI.create_virtual_account(user)

        if acc_data:
            wallet.account_number = acc_data['account_number']
            wallet.bank_name = acc_data['bank_name']
            wallet.bank_code = acc_data['bank_code']
            wallet.save()
            logger.info("UpdateBVN: virtual account %s created", acc_data['account_number'])
            return Response({"message": "Success", "account": acc_data}, status=200)

        # One last check — the signal's background thread may have finished.
        wallet.refresh_from_db()
        if wallet.account_number:
            logger.info("UpdateBVN: signal completed after our API call, using its result")
            return Response({
                "message": "Success",
                "account": {
                    "account_number": wallet.account_number,
                    "bank_name": wallet.bank_name,
                    "bank_code": wallet.bank_code,
                },
            }, status=200)

        logger.error("UpdateBVN: Monnify creation failed: %s", error_msg)
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
            # Block unapproved accounts
            if user.kyc_status == User.KycStatus.REJECTED:
                logger.warning("LOGIN denied: rejected — email=%r", email)
                return Response({
                    "error": "Your account has been rejected. Please contact support for assistance.",
                }, status=status.HTTP_403_FORBIDDEN)

            login(request, user)

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
            logger.info("LOGIN 200: email=%r role=%s", email, user_role)
            return Response(payload, status=status.HTTP_200_OK)
            
        return Response({"error": "Invalid email or password credentials"}, status=status.HTTP_401_UNAUTHORIZED)