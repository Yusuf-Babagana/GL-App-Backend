"""
User notifications: Expo push (the app registers each user's token on their profile)
plus email. Best effort by design: a notification problem must never break, delay or
roll back a payment, so every failure is logged and swallowed.

    notify_user(user, "Dispute opened", "Order #4 was disputed.", data={"order_id": 4})
    notify_admins("Dispute needs review", "Order #4 ...")

Sending runs on a background thread so the request returns immediately. Set
NOTIFY_ASYNC=False (the tests do) to send inline.
"""
import logging
import threading

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger('payments')

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'


def _send_push(token, title, body, data):
    if not token or not str(token).startswith(('ExponentPushToken', 'ExpoPushToken')):
        return
    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            json={'to': token, 'title': title, 'body': body, 'data': data or {}, 'sound': 'default'},
            timeout=5,
        )
        if resp.status_code != 200:
            logger.warning("Expo push rejected (%s): %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("Expo push failed: %s", e)


def _send_email(address, subject, body):
    if not address:
        return
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [address], fail_silently=False)
    except Exception as e:
        logger.warning("Notification email to %s failed: %s", address, e)


def _dispatch(fn, *args):
    if getattr(settings, 'NOTIFY_ASYNC', True):
        threading.Thread(target=fn, args=args, daemon=True).start()
    else:
        fn(*args)


def notify_user(user, title, body, data=None):
    """Push + email one user. Safe to call from anywhere, including right after a payment."""
    if user is None:
        return
    try:
        token, email = getattr(user, 'push_token', None), getattr(user, 'email', None)

        def work():
            _send_push(token, title, body, data)
            _send_email(email, f"GLAPP: {title}", body)

        _dispatch(work)
    except Exception as e:
        logger.warning("notify_user failed: %s", e)


def notify_admins(title, body):
    """Email the addresses in ADMIN_EMAILS."""
    try:
        addresses = [e for _, e in getattr(settings, 'ADMINS', [])]
        if not addresses:
            return

        def work():
            for address in addresses:
                _send_email(address, f"GLAPP admin: {title}", body)

        _dispatch(work)
    except Exception as e:
        logger.warning("notify_admins failed: %s", e)
