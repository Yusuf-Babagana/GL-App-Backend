import csv
import uuid
from datetime import datetime
from django.http import HttpResponse
from django.contrib import admin
from .models import Wallet, Transaction, WithdrawalRequest


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['pk', 'user', 'amount', 'bank_name', 'account_number', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__email', 'account_number', 'bank_name']
    actions = ['export_to_monnify_csv']

    @admin.action(description='Export selected PENDING requests as Monnify Bulk CSV')
    def export_to_monnify_csv(self, request, queryset):
        pending = queryset.filter(status=WithdrawalRequest.StatusChoices.PENDING)
        if not pending.exists():
            self.message_user(request, 'No PENDING requests selected.')
            return

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="monnify_payouts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Amount', 'Bank Code', 'Account Number', 'Narration', 'Reference'])

        for wreq in pending:
            reference = f"GLB-{wreq.pk}-{uuid.uuid4().hex[:8]}"
            writer.writerow([
                float(wreq.amount),
                wreq.bank_code,
                wreq.account_number,
                f"GLAPP Payout #{wreq.pk}",
                reference,
            ])

        return response


admin.site.register(Wallet)
admin.site.register(Transaction)
