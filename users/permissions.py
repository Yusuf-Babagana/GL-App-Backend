from rest_framework import permissions

class IsVerifiedUser(permissions.BasePermission):
    """
    Blocks access to core features unless user's kyc_status is 'verified'.
    """
    message = "Your account must be verified before performing this action."

    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.kyc_status == 'verified'
        )