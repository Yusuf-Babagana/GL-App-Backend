import csv
import uuid
from datetime import datetime
from django.http import HttpResponse
from django.contrib import admin
from .models import Wallet, Transaction, WithdrawalTicket, DataMarkup, DataPlanPrice


@admin.register(WithdrawalTicket)
class WithdrawalTicketAdmin(admin.ModelAdmin):
    list_display = ['pk', 'user', 'amount', 'bank_name', 'account_number', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__email', 'account_number', 'bank_name']
    actions = ['export_to_monnify_csv']

    @admin.action(description='Export selected PENDING tickets as Monnify Bulk CSV')
    def export_to_monnify_csv(self, request, queryset):
        pending = queryset.filter(status=WithdrawalTicket.StatusChoices.PENDING)
        if not pending.exists():
            self.message_user(request, 'No PENDING tickets selected.')
            return

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="monnify_payouts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow([
            'Amount', 'DestinationBankCode', 'DestinationAccountNumber',
            'DestinationAccountName', 'Narration', 'Reference',
        ])

        for ticket in pending:
            reference = f"GLB-{ticket.pk}-{uuid.uuid4().hex[:8]}"
            writer.writerow([
                float(ticket.amount),
                ticket.bank_code,
                ticket.account_number,
                ticket.account_name,
                f"GLAPP Payout #{ticket.pk}",
                reference,
            ])

        return response


admin.site.register(Wallet)
admin.site.register(Transaction)

@admin.register(DataMarkup)
class DataMarkupAdmin(admin.ModelAdmin):
    list_display = ['network', 'network_label', 'markup_amount', 'is_active', 'updated_at']
    list_editable = ['markup_amount', 'is_active']
    list_filter = ['is_active']

@admin.register(DataPlanPrice)
class DataPlanPriceAdmin(admin.ModelAdmin):
    list_display = ['network', 'variation_code', 'plan_name', 'selling_price', 'is_active', 'updated_at']
    list_editable = ['is_active', 'selling_price']
    list_filter = ['network', 'is_active']
    search_fields = ['network', 'variation_code', 'plan_name']
