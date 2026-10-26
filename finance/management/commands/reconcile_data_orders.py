from django.core.management.base import BaseCommand

from finance.reconcile import reconcile_pending_data_orders


class Command(BaseCommand):
    help = "Settle Pending data orders whose webhook never arrived."

    def handle(self, *args, **options):
        settled = reconcile_pending_data_orders(max_orders=50)
        self.stdout.write(f"Settled {settled} pending data order(s).")
