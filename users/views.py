from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, RegistrationSerializer, KYCUploadSerializer

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
    """
    Upload ID and Selfie. Auto-sets status to 'pending'.
    """
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser) # To handle image uploads

    def post(self, request):
        user = request.user
        serializer = KYCUploadSerializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            # Auto-update status
            user.kyc_status = User.KycStatus.PENDING
            user.save()
            return Response({"message": "KYC submitted for review."}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)