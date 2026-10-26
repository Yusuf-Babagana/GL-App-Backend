import json
import sys

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from finance.health import build_health_report


class Command(BaseCommand):
    help = ("Print the payment health report. Exits 1 if anything needs attention. "
            "Schedule it hourly with --email to be alerted.")

    def add_arguments(self, parser):
        parser.add_argument('--email', action='store_true', help="Email ADMIN_EMAILS when there are alerts.")
        parser.add_argument('--json', action='store_true')
        parser.add_argument('--skip-provider', action='store_true', help="Don't call BT DataPlug for its balance.")

    def handle(self, *args, **o):
        report = build_health_report(check_provider=not o['skip_provider'])
        if o['json']:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self.stdout.write("HEALTHY" if report['healthy'] else "NEEDS ATTENTION")
            for a in report['alerts']:
                self.stdout.write(f"  ! {a}")
            self.stdout.write(f"  purchases 24h: {report['purchases_24h']}")
            self.stdout.write(f"  disputes: {report['disputes']}")
            self.stdout.write(f"  provider: {report['provider']}")
        if report['alerts'] and o['email'] and settings.ADMINS:
            send_mail("GLAPP payment alerts", "\n".join(f"- {a}" for a in report['alerts']),
                      settings.DEFAULT_FROM_EMAIL, [e for _, e in settings.ADMINS])
        if report['alerts']:
            sys.exit(1)
