import logging
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()


class Command(BaseCommand):
    help = "Anonymizes users whose deletion request is older than the grace period."

    def handle(self, *args, **options):
        grace_days = settings.ACCOUNT_DELETION_GRACE_PERIOD_DAYS
        cutoff = timezone.now() - timedelta(days=grace_days)

        users = User.objects.filter(
            is_deactivation_pending=True,
            deletion_requested_at__lte=cutoff,
        )

        count = 0
        for user in users:
            try:
                original_email = user.email
                user.email = f"deleted_user_{user.id}@globalink.com"
                user.full_name = "Deleted User"
                user.first_name = ""
                user.last_name = ""
                user.phone_number = None
                user.profile_image = None
                user.push_token = None
                user.bvn = None
                user.nin = None
                user.kyc_status = "unverified"
                user.id_document_type = None
                user.id_document_image = None
                user.selfie_image = None
                user.rejection_reason = None
                user.transaction_pin = None
                user.is_active = False
                user.is_deactivation_pending = False
                user.set_unusable_password()
                user.save()

                logger.info(f"Anonymized user {user.id} (was: {original_email})")
                count += 1
            except Exception as e:
                logger.error(f"Failed to anonymize user {user.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Anonymized {count} user(s)."))
