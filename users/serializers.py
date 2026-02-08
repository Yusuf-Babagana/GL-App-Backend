from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Address

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """
    Standard User Serializer for reading user data.
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone_number', 'profile_image', 
            'roles', 'active_role', 'kyc_status', 'language_preference','is_staff','push_token','is_online','last_seen'
        ]
        read_only_fields = ['id', 'roles', 'kyc_status']

class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'full_name', 'password', 'phone_number']

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['email'],
            full_name=validated_data['full_name'],
            phone_number=validated_data.get('phone_number'),
            password=validated_data['password']
        )
        
        # Yusuf, we default them to buyer here
        user.roles = ['buyer'] 
        user.active_role = 'buyer'
        user.save()
        return user

class KYCUploadSerializer(serializers.ModelSerializer):
    """
    Handles uploading ID and Selfie for verification.
    """
    class Meta:
        model = User
        # These names MUST match the keys in the React Native formData.append()
        fields = ['id_document_type', 'id_document_image', 'selfie_image']
        
    def validate(self, data):
        # Ensure both images are present
        if not data.get('id_document_image') or not data.get('selfie_image'):
            raise serializers.ValidationError("Both ID and Selfie are required.")
        return data

class AdminKYCSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for the Admin Dashboard to review documents.
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone_number', 
            'kyc_status', 'id_document_type', 
            'id_document_image', 'selfie_image', 'date_joined'
        ]

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        exclude = ['user'] # User is inferred from request