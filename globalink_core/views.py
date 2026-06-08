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
from django.db.models import Sum, Count
from django.db.utils import OperationalError
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from finance.models import Wallet, WithdrawalTicket, PlatformRevenue, DataMarkup, DataPlanPrice
from finance.nellobyte import NellobyteClient
from market.models import Shop, Order

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

        total_orders = Order.objects.count()
        pending_kyc_users = User.objects.filter(kyc_status='pending')
        pending_kyc_count = pending_kyc_users.count()
        total_active_shops = Shop.objects.filter(is_active=True).count()

        context['pending_tickets'] = pending_tickets
        context['total_pending_amount'] = total_pending_amount
        context['total_locked_escrow'] = total_locked_escrow
        context['total_users_count'] = total_users_count
        context['pending_shops'] = pending_shops
        context['recent_registrations'] = recent_registrations
        context['total_commission'] = platform_revenue.total_commission
        context['total_orders'] = total_orders
        context['pending_kyc_users'] = pending_kyc_users
        context['pending_kyc_count'] = pending_kyc_count
        context['total_active_shops'] = total_active_shops
        try:
            context['data_markups'] = list(DataMarkup.objects.all().order_by('network'))
        except OperationalError:
            context['data_markups'] = []
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


@method_decorator(csrf_exempt, name='dispatch')
class AdminDataPricingView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'admin_login'

    SERVICE_TO_NETWORK = {
        'mtn-data': 'MTN',
        'glo-data': 'Glo',
        'airtel-data': 'Airtel',
        '9mobile-data': '9mobile',
    }

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def _fetch_price_preview(self):
        preview = []
        for svc, net in self.SERVICE_TO_NETWORK.items():
            entry = {'network': svc, 'network_label': net, 'samples': [], 'error': None}
            try:
                client = NellobyteClient()
                plans = client.fetch_all_variations(net)
                factor = 1.10
                try:
                    dm = DataMarkup.objects.get(network=svc, is_active=True)
                    factor = float(dm.price_factor)
                except DataMarkup.DoesNotExist:
                    pass
                for plan in plans[:3]:
                    raw_price = None
                    for key in ('PRODUCT_AMOUNT', 'price', 'Price', 'amount', 'Amount', 'variation_amount'):
                        val = plan.get(key)
                        if val is not None:
                            raw_price = val
                            break
                    if raw_price is not None:
                        original = float(str(raw_price).replace(',', ''))
                        entry['samples'].append({
                            'name': plan.get('PRODUCT_NAME', plan.get('name', 'Plan')),
                            'original_price': str(round(original, 2)),
                            'factor': str(round(factor, 2)),
                            'selling_price': str(round(original * factor, 2)),
                        })
            except Exception as e:
                entry['error'] = str(e)
            preview.append(entry)
        return preview

    def get(self, request):
        try:
            markups = DataMarkup.objects.all().order_by('network')
            data = [{
                'id': m.id,
                'network': m.network,
                'network_label': m.network_label,
                'price_factor': str(m.price_factor),
                'is_active': m.is_active,
            } for m in markups]
        except OperationalError:
            data = []

        price_preview = self._fetch_price_preview() if request.GET.get('refresh') == 'true' else []
        return JsonResponse({'markups': data, 'price_preview': price_preview})

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        markup_id = body.get('id')
        price_factor = body.get('price_factor')
        is_active = body.get('is_active')

        if not markup_id:
            return JsonResponse({'error': 'Missing markup id'}, status=400)

        try:
            markup = DataMarkup.objects.get(id=markup_id)
        except OperationalError:
            return JsonResponse({'error': 'Database table not ready. Run migrations.'}, status=503)
        except DataMarkup.DoesNotExist:
            return JsonResponse({'error': 'Markup not found'}, status=404)

        if price_factor is not None:
            try:
                pf = float(price_factor)
                if pf <= 0:
                    raise ValueError
                markup.price_factor = pf
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Invalid price factor (must be a positive number)'}, status=400)

        if is_active is not None:
            markup.is_active = bool(is_active)

        markup.save()

        from finance.views import DataVariationsView
        DataVariationsView._markup_cache.pop(markup.network, None)

        return JsonResponse({
            'status': 'success',
            'markup': {
                'id': markup.id,
                'network': markup.network,
                'network_label': markup.network_label,
                'price_factor': str(markup.price_factor),
                'is_active': markup.is_active,
            }
        })


NETWORK_INFO = {
    'mtn-data':    ('MTN',     'MTN'),
    'glo-data':    ('Glo',     'Glo'),
    'airtel-data': ('Airtel',  'Airtel'),
    '9mobile-data':('9mobile', '9mobile'),
}


@method_decorator(csrf_exempt, name='dispatch')
class AdminDataPlansView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'admin_login'

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get(self, request):
        client = NellobyteClient()
        overrides = {}
        try:
            for dpp in DataPlanPrice.objects.filter(is_active=True):
                overrides[(dpp.network, dpp.variation_code)] = dpp
        except OperationalError:
            overrides = {}

        all_plans = []
        for svc, (net_key, label) in NETWORK_INFO.items():
            try:
                plans = client.fetch_all_variations(net_key)
            except Exception:
                continue
            factor = 1.10
            try:
                dm = DataMarkup.objects.get(network=svc, is_active=True)
                factor = float(dm.price_factor)
            except (DataMarkup.DoesNotExist, OperationalError):
                pass
            for plan in plans:
                code = str(plan.get('PRODUCT_ID', '') or plan.get('variation_code', '') or '')
                name = str(plan.get('PRODUCT_NAME', '') or plan.get('name', '') or '')
                raw_price = None
                for key in ('PRODUCT_AMOUNT', 'price', 'Price', 'amount', 'Amount', 'variation_amount'):
                    val = plan.get(key)
                    if val is not None:
                        raw_price = val
                        break
                if raw_price is None:
                    continue
                original = float(str(raw_price).replace(',', ''))
                key = (svc, code)
                if key in overrides:
                    dpp = overrides[key]
                    sp = float(dpp.selling_price) if dpp.selling_price is not None else None
                    all_plans.append({
                        'id': dpp.id,
                        'network': svc,
                        'network_label': label,
                        'variation_code': code,
                        'plan_name': name,
                        'original_price': str(round(original, 2)),
                        'selling_price': str(round(sp, 2)) if sp is not None else None,
                        'overridden': sp is not None,
                    })
                else:
                    sp = round(original * factor, 2)
                    all_plans.append({
                        'id': None,
                        'network': svc,
                        'network_label': label,
                        'variation_code': code,
                        'plan_name': name,
                        'original_price': str(round(original, 2)),
                        'selling_price': str(sp),
                        'overridden': False,
                    })
        return JsonResponse({'plans': all_plans})

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        entries = body.get('overrides', [])
        saved = 0
        for entry in entries:
            network = entry.get('network')
            code = entry.get('variation_code')
            sp_raw = entry.get('selling_price')
            if not network or not code:
                continue
            try:
                if sp_raw is not None:
                    sp = Decimal(str(sp_raw))
                    dpp, created = DataPlanPrice.objects.update_or_create(
                        network=network,
                        variation_code=code,
                        defaults={'selling_price': sp, 'is_active': True},
                    )
                else:
                    DataPlanPrice.objects.filter(
                        network=network, variation_code=code
                    ).update(is_active=False)
                saved += 1
            except Exception:
                continue
        return JsonResponse({'status': 'success', 'saved': saved})
