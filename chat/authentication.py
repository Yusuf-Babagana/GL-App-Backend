from django.contrib.auth import get_user_model
from django.db import close_old_connections
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class TokenAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        close_old_connections()
        query_string = scope.get("query_string", b"").decode()
        params = dict(
            param.split("=") for param in query_string.split("&") if param
        )
        token = params.get("token")

        if token is None:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if token:
            try:
                access_token = AccessToken(token)
                user = await User.objects.aget(id=access_token["user_id"])
                scope["user"] = user
            except Exception:
                scope["user"] = None
        else:
            scope["user"] = None

        return await self.inner(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(inner)
