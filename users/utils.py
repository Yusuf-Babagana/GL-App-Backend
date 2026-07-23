import logging
import threading
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _send_email_async(subject, message, recipient_list, html_message=None):
    try:
        import requests
        try:
            egress_ip = requests.get('https://api.ipify.org', timeout=5).text
            logger.info(f"DEBUG: web app egress IP is {egress_ip}")
        except Exception as ip_err:
            logger.error(f"DEBUG: failed to fetch egress IP: {ip_err}")

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email sent to {recipient_list}")
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_list}: {e}")


def send_email(subject, message, recipient_list, html_message=None):
    thread = threading.Thread(
        target=_send_email_async,
        args=(subject, message, recipient_list, html_message),
        daemon=True,
    )
    thread.start()


def send_deletion_requested_email(user):
    subject = "Account Deletion Request Confirmed"
    cancel_url = f"{settings.FRONTEND_URL}/cancel-deletion/?token={user.email}"
    message = (
        f"Hi {user.full_name or user.email},\n\n"
        f"We received a request to delete your Globalink account.\n"
        f"Your account will be permanently deleted in {settings.ACCOUNT_DELETION_GRACE_PERIOD_DAYS} days.\n\n"
        f"If you did not make this request, you can cancel it here:\n"
        f"{cancel_url}\n\n"
        f"If you do not cancel, your account will be anonymized after {settings.ACCOUNT_DELETION_GRACE_PERIOD_DAYS} days.\n\n"
        f"Thank you,\nGlobalink Team"
    )
    html_message = render_to_string("emails/deletion_requested.html", {
        "user": user,
        "cancel_url": cancel_url,
        "grace_period_days": settings.ACCOUNT_DELETION_GRACE_PERIOD_DAYS,
    })
    send_email(subject, message, [user.email], html_message=html_message)


def send_password_reset_email(user, code):
    from .models import PasswordResetOTP
    subject = "Your Globalink Password Reset Code"
    message = (
        f"Hi {user.full_name or user.email},\n\n"
        f"Your password reset code is: {code}\n\n"
        f"This code expires in {PasswordResetOTP.VALIDITY_MINUTES} minutes. "
        f"If you did not request this, you can safely ignore this email.\n\n"
        f"Thank you,\nGlobalink Team"
    )
    send_email(subject, message, [user.email])


def send_deletion_cancelled_email(user):
    subject = "Account Deletion Cancelled"
    message = (
        f"Hi {user.full_name or user.email},\n\n"
        f"Your account deletion request has been cancelled.\n"
        f"Your account remains active and all your data is safe.\n\n"
        f"Thank you,\nGlobalink Team"
    )
    send_email(subject, message, [user.email])
