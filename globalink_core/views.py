import csv
import uuid
from datetime import datetime
from decimal import Decimal
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.base import TemplateView
from django.views import View
from django.db.models import Sum
from django.contrib.auth import get_user_model
from finance.models import Wallet, WithdrawalTicket, PlatformRevenue
from market.models import Shop

User = get_user_model()


class AdminDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'admin/dashboard.html'
    login_url = 'admin_login'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        pending_tickets = WithdrawalTicket.objects.filter(
            status=WithdrawalTicket.StatusChoices.PENDING
        ).select_related('user').order_by('-created_at')

        total_pending_amount = pending_tickets.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        total_locked_escrow = Wallet.objects.aggregate(
            total=Sum('locked_balance')
        )['total'] or Decimal('0.00')

        total_users_count = User.objects.count()

        pending_shops = Shop.objects.filter(
            is_active=False
        ).select_related('owner').order_by('-created_at')

        recent_registrations = User.objects.all().order_by('-date_joined')[:10]

        platform_revenue = PlatformRevenue.get_singleton()

        context['pending_tickets'] = pending_tickets
        context['total_pending_amount'] = total_pending_amount
        context['total_locked_escrow'] = total_locked_escrow
        context['total_users_count'] = total_users_count
        context['pending_shops'] = pending_shops
        context['recent_registrations'] = recent_registrations
        context['total_commission'] = platform_revenue.total_commission
        return context


class AdminShopVerificationView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'admin_login'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, shop_id):
        shop = get_object_or_404(Shop, pk=shop_id)
        action = request.POST.get('action') or request.GET.get('action')

        if action == 'approve':
            with transaction.atomic():
                shop.is_active = True
                shop.save()
                owner = shop.owner
                owner.active_role = 'seller'
                owner.save()
            return JsonResponse({'status': 'success', 'message': f"'{shop.name}' approved and owner elevated to Seller."})

        elif action == 'reject':
            with transaction.atomic():
                shop.delete()
            return JsonResponse({'status': 'success', 'message': 'Shop application rejected and removed.'})

        return JsonResponse({'status': 'error', 'message': 'Invalid action.'}, status=400)


class MonnifyBatchCsvExportView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'admin_login'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get(self, request):
        pending = WithdrawalTicket.objects.filter(
            status=WithdrawalTicket.StatusChoices.PENDING
        ).order_by('-created_at')

        if not pending.exists():
            response = HttpResponse(content_type='text/plain')
            response.write('No pending withdrawal tickets to export.')
            return response

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
            ref = f"GLB-{ticket.pk}-{uuid.uuid4().hex[:8]}"
            writer.writerow([
                float(ticket.amount),
                ticket.bank_code,
                ticket.account_number,
                ticket.account_name or 'N/A',
                f"GLAPP Payout #{ticket.pk}",
                ref,
            ])

        return response


class WithdrawalTicketUpdateStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'admin_login'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def post(self, request, ticket_id):
        ticket = get_object_or_404(WithdrawalTicket, pk=ticket_id)
        action = request.POST.get('action')

        if ticket.status != WithdrawalTicket.StatusChoices.PENDING:
            return HttpResponse('Ticket already processed.', status=400)

        if action == 'approve':
            ticket.status = WithdrawalTicket.StatusChoices.SUCCESSFUL
            ticket.save()
            return HttpResponse('approved')

        elif action == 'reject':
            with transaction.atomic():
                wallet, _ = Wallet.objects.select_for_update().get_or_create(
                    user=ticket.user
                )
                wallet.available_balance += ticket.amount
                wallet.save()

                ticket.status = WithdrawalTicket.StatusChoices.REJECTED
                ticket.save()
            return HttpResponse('rejected')

        return HttpResponse('Invalid action.', status=400)
