import json
import logging
import re
from django.contrib.auth import get_user_model
from datetime import datetime
import pytz
import uuid
import hashlib
import hmac
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import permissions, status, generics
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Wallet, Transaction, BankAccount, WithdrawalTicket, PlatformRevenue, DataMarkup, DataPlanPrice, MONNIFY_DEPOSIT_RATE, MONNIFY_DEPOSIT_CAP
from market.models import Order
from .serializers import WalletSerializer, TransactionSerializer, DataHistorySerializer, WithdrawalTicketSerializer

MONNIFY_DEPOSIT_RATE = MONNIFY_DEPOSIT_RATE
MONNIFY_DEPOSIT_CAP  = MONNIFY_DEPOSIT_CAP

from users.permissions import IsVerifiedUser
from .utils import MonnifyAPI

from .vtpass import VTPassClient  # Add this near your other imports

logger = logging.getLogger(__name__)

class TransactionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(wallet=self.request.user.wallet).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        # Same safety net as DataHistoryView: the wallet screens read this
        # endpoint, so settle stuck Pending data orders here too.
        try:
            from .reconcile import reconcile_pending_data_orders
            reconcile_pending_data_orders(wallet=request.user.wallet, max_orders=5)
        except Exception as e:
            logger.error(f"Transaction list reconcile failed: {e}")
        return super().list(request, *args, **kwargs)

class WalletDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            # 1. get_or_create ensures no crash if the user somehow has no wallet
            wallet, created = Wallet.objects.get_or_create(user=request.user)
            
            # 2. Safety Net for Virtual Account
            if not wallet.account_number:
                try:
                    acc_data, acc_error = MonnifyAPI.create_virtual_account(request.user)
                    if acc_data:
                        wallet.account_number = acc_data.get('account_number')
                        wallet.bank_name = acc_data.get('bank_name')
                        wallet.bank_code = acc_data.get('bank_code')
                        wallet.account_reference = acc_data.get('account_reference')
                        wallet.save()
                except Exception as e:
                    logger.error(f"Monnify Account Generation Error: {e}")

            # 3. Serialize and return
            serializer = WalletSerializer(wallet)
            return Response(serializer.data)
            
        except Exception as e:
            # This will show up in your PythonAnywhere "Error Log"
            logger.error(f"WalletDetailView 500 Error: {str(e)}")
            return Response({"error": "Internal Server Error", "details": str(e)}, status=500)



from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

class MonnifyWebhookView(APIView):
    permission_classes = [AllowAny] # Publicly accessible for Monnify

    def post(self, request):
        # 1. Security Check: Verify Monnify Signature
        signature = request.headers.get('monnify-signature')
        if not signature:
            return Response({"error": "No signature"}, status=status.HTTP_400_BAD_REQUEST)

        # SECURE: Recompute hash and use compare_digest
        computed_hash = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode(),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, signature):
            logger.warning(f"Invalid Webhook Signature attempt from {request.META.get('REMOTE_ADDR')}")
            return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data
        event_type = data.get('eventType')
        event_data = data.get('eventData', {})
        
        # Log for debugging
        logger.info(f"WEBHOOK RECEIVED: {event_type}")
        
        # CASE 1: Incoming Deposit (User funding wallet or Order Checkout)
        if event_type == 'SUCCESSFUL_TRANSACTION':
            payment_ref = event_data.get('paymentReference')
            amount_paid = Decimal(str(event_data.get('amountPaid', 0)))
            settlement_amt = Decimal(str(event_data.get('settlementAmount', 0)))
            fee = amount_paid - settlement_amt
            
            # --- FEATURE 1: Order Checkout Logic ---
            try:
                with transaction.atomic():
                    # Find the order by reference (using monnify_reference per our models)
                    order = Order.objects.get(monnify_reference=payment_ref)
                    
                    if order.payment_status != Order.PaymentStatus.PAID:
                        # Update order status
                        order.payment_status = Order.PaymentStatus.PAID
                        order.save()

                        # Update Seller Stats (This fuels your Dashboard image)
                        shop = order.shop
                        if shop:
                            shop.total_sales += int(amount_paid)
                            shop.save()
                    
                logger.info(f"✅ Order marked as PAID via Monnify Webhook (Ref: {payment_ref})")
                return Response({"status": "success"}, status=200)
            except Order.DoesNotExist:
                pass # Fall through to Virtual Account Wallet Funding
                
            # --- FEATURE 2: Virtual Account Wallet Funding Logic ---
            account_ref = event_data.get('product', {}).get('reference') 
            if account_ref:
                try:
                    with transaction.atomic():
                        wallet = Wallet.objects.select_for_update().get(account_reference=account_ref)
                        
                        if not Transaction.objects.filter(reference=payment_ref).exists():
                            processing_fee = min(
                                settlement_amt * MONNIFY_DEPOSIT_RATE,
                                MONNIFY_DEPOSIT_CAP
                            )
                            net_credit = settlement_amt - processing_fee

                            wallet.available_balance += net_credit
                            wallet.save()
                            
                            Transaction.objects.create(
                                wallet=wallet,
                                amount=net_credit,
                                transaction_type=Transaction.TransactionType.DEPOSIT,
                                status=Transaction.Status.SUCCESS,
                                reference=payment_ref,
                                description=f"Bank Deposit (Fee: ₦{processing_fee})" 
                            )
                    logger.info(f"✅ Wallet {wallet.id} credited with ₦{net_credit} (net of ₦{processing_fee} processing fee)")
                    return Response({"status": "success"}, status=200)
                except Wallet.DoesNotExist:
                    logger.error(f"❌ Webhook Error: Wallet with reference {account_ref} not found.")
                    return Response({"error": "Wallet not found"}, status=status.HTTP_404_NOT_FOUND)
                except Exception as e:
                    logger.error(f"❌ Webhook Processing Error: {str(e)}")
                    return Response({"error": "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({"error": "Unhandled payment reference"}, status=404)

        # CASE 2: Outgoing Withdrawal (Monnify finished sending money to bank)
        elif event_type == 'DISBURSEMENT_SUCCESS':
            ref = event_data.get('reference')
            try:
                with transaction.atomic():
                    ledger = Transaction.objects.select_for_update().filter(reference=ref).first()
                    if ledger is None:
                        logger.error(f"Disbursement success webhook for unknown ref {ref}")
                    elif ledger.status == Transaction.Status.FAILED:
                        # Already refunded to the wallet but the bank transfer went
                        # through: do NOT flip to SUCCESS silently, flag for manual review.
                        logger.critical(
                            f"DOUBLE-PAYOUT RISK: ref {ref} was refunded (FAILED) but Monnify reports success"
                        )
                    else:
                        ledger.status = Transaction.Status.SUCCESS
                        ledger.save(update_fields=['status'])
                        logger.info(f"✅ Disbursement successful for ref {ref}")
            except Exception as e:
                logger.error(f"❌ Disbursement success webhook failure: {e}")
                return Response({"error": "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response({"status": "success"}, status=status.HTTP_200_OK)

        elif event_type == 'DISBURSEMENT_FAILED':
            ref = event_data.get('reference')
            try:
                with transaction.atomic():
                    ledger = Transaction.objects.select_for_update().filter(reference=ref).first()
                    if ledger is None:
                        logger.error(f"Disbursement failed webhook for unknown ref {ref}")
                    elif (
                        ledger.transaction_type == Transaction.TransactionType.WITHDRAWAL
                        and ledger.status != Transaction.Status.FAILED
                    ):
                        # Withdrawals debit the wallet up front (PENDING or SUCCESS
                        # alike), so both states must be refunded — exactly once.
                        wallet = Wallet.objects.select_for_update().get(pk=ledger.wallet_id)
                        wallet.available_balance += abs(ledger.amount)
                        wallet.save()
                        ledger.status = Transaction.Status.FAILED
                        ledger.description += " (Failed: Refunded)"
                        ledger.save()
                        logger.warning(f"⚠️ Disbursement failed and refunded for ref {ref}")
            except Exception as e:
                logger.error(f"❌ Webhook Refund failure: {e}")
                # Non-2xx so Monnify retries instead of silently losing the refund.
                return Response({"error": "Internal Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "success"}, status=200)


from .btdataplug import BTDataPlugClient, BTDataPlugError, verify_webhook_signature
from .nellobyte import NellobyteClient  # deposit webhook only
from market.pagination import MarketPageNumberPagination

class DataPurchaseView(APIView):
    """
    Handles Data Bundle purchases using BTDataPlugClient.
    Fetches the live price from BT DataPlug + admin markup on the server.
    """
    permission_classes = [permissions.IsAuthenticated]

    SERVICE_TO_NETWORK = {
        'mtn-data': 'MTN',
        'glo-data': 'Glo',
        'airtel-data': 'Airtel',
        '9mobile-data': '9mobile',
    }

    def _fetch_live_price(self, service_id, variation_code):
        network_key = self.SERVICE_TO_NETWORK.get(service_id)
        if not network_key:
            return None, f"Unknown service: {service_id}"

        client = BTDataPlugClient()
        plans = client.fetch_all_variations(network_key)

        matched = None
        for plan in plans:
            pid = str(plan.get('PRODUCT_ID', '') or plan.get('ID', '') or '')
            if pid == variation_code:
                matched = plan
                break

        if not matched:
            return None, f"Plan '{variation_code}' not found for {service_id}"

        plan_type = str(matched.get('type') or matched.get('Type') or '').lower()
        plan_name = str(matched.get('PRODUCT_NAME') or matched.get('name') or matched.get('Name') or '').lower()
        if 'airtime' in plan_type or 'airtime' in plan_name:
            return None, f"Plan '{variation_code}' is an airtime plan, not data"

        raw_price = None
        for key in ('PRODUCT_AMOUNT', 'price', 'Price', 'amount', 'Amount', 'variation_amount'):
            val = matched.get(key)
            if val is not None:
                raw_price = val
                break

        if raw_price is None:
            return None, "Could not determine plan price from provider"

        original_price = float(str(raw_price).replace(',', ''))
        # Check per-plan override first
        try:
            dpp = DataPlanPrice.objects.get(
                network=service_id, variation_code=variation_code,
                is_active=True, selling_price__isnull=False
            )
            verified = round(float(dpp.selling_price), 2)
            return Decimal(str(verified)), None
        except DataPlanPrice.DoesNotExist:
            pass
        factor = 1.10
        try:
            dm = DataMarkup.objects.get(network=service_id, is_active=True)
            factor = float(dm.price_factor)
        except DataMarkup.DoesNotExist:
            pass

        verified = round(original_price * factor, 2)
        return Decimal(str(verified)), None

    def post(self, request):
        logger.info(f"Data Purchase Request: {request.data}")
        service_id = request.data.get('service_id')
        data_plan = request.data.get('variation_code')
        phone = request.data.get('phone')

        if not all([service_id, data_plan, phone]):
            logger.error("Data Purchase 400: Missing required fields.")
            return Response({"error": "Missing service_id, variation_code, or phone."}, status=400)

        # Fetch live price from BT DataPlug + admin markup
        amount, error = self._fetch_live_price(service_id, data_plan)
        if error:
            logger.error(f"Data Purchase 400: Price fetch failed: {error}")
            return Response({"error": error}, status=400)

        request_id = str(uuid.uuid4().hex)[:12]

        # Reject purchase if this plan has been disabled by the auto‑disable system
        if DataPlanPrice.objects.filter(
            network=service_id, variation_code=data_plan, is_active=False
        ).exists():
            logger.error(f"Data Purchase 400: Plan {service_id}/{data_plan} is currently unavailable")
            return Response({
                "error": "This data plan is temporarily unavailable. Please try another plan."
            }, status=400)

        # Check balance first (no deduction yet)
        try:
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return Response({"error": "Wallet not found."}, status=400)
        if wallet.available_balance < amount:
            logger.error(f"Data Purchase 400: Insufficient Balance. Need {amount}, have {wallet.available_balance}")
            return Response({"error": "Insufficient wallet balance."}, status=400)

        # Call the provider FIRST before touching wallet. request_id is the
        # idempotency key, so a retry of this same order can never double-charge.
        desc = f"Data: {service_id.upper()} ({data_plan}) to {phone}"
        try:
            client = BTDataPlugClient()
            logger.info(f"Calling BTDataPlug with req_id={request_id}, svc={service_id}, plan={data_plan}, ph={phone}")
            order = client.purchase_data(request_id, data_plan, phone)
            order_status = order.get('status')

            if order_status in ('successful', 'pending'):
                is_success = order_status == 'successful'
                with transaction.atomic():
                    wallet = Wallet.objects.select_for_update().get(user=request.user)
                    if wallet.available_balance < amount:
                        return Response({"error": "Insufficient wallet balance."}, status=400)

                    wallet.available_balance -= amount
                    wallet.save()

                    Transaction.objects.create(
                        wallet=wallet,
                        amount=-amount,
                        transaction_type=Transaction.TransactionType.BILL_PAYMENT,
                        status=Transaction.Status.SUCCESS if is_success else Transaction.Status.PENDING,
                        description=desc if is_success else f"{desc} (Pending)",
                        reference=request_id
                    )

                if is_success:
                    return Response({
                        "message": "Data purchase successful!",
                        "order_id": order.get('reference'),
                        "new_balance": float(wallet.available_balance)
                    }, status=200)
                return Response({
                    "message": "Order submitted for processing. Check history for status updates.",
                    "order_id": order.get('reference'),
                    "new_balance": float(wallet.available_balance)
                }, status=202)

            error_msg = order.get('failure_reason') or 'Provider rejected request'
            return self._record_failure(wallet, desc, request_id, error_msg)

        except BTDataPlugError as e:
            if e.code in ('purchase_failed', 'validation_error', 'insufficient_funds',
                          'service_not_permitted', 'service_unavailable'):
                # Provider clearly did not take the order (and refunded itself if it charged).
                logger.error(f"Data Purchase 400: BTDataPlug Error: {e} | Code: {e.code}")
                if e.code == 'insufficient_funds':
                    # Our provider wallet is empty -- not the user's problem to see.
                    msg = "Service temporarily unavailable. Please try again later."
                else:
                    msg = str(e)
                return self._record_failure(wallet, desc, request_id, msg)
            # Anything else (timeout, 5xx, request_in_progress, ...) is ambiguous.
            return self._reserve_pending(request, amount, desc, request_id, e)
        except Exception as e:
            return self._reserve_pending(request, amount, desc, request_id, e)

    def _record_failure(self, wallet, desc, request_id, error_msg):
        Transaction.objects.create(
            wallet=wallet,
            amount=0,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT,
            status=Transaction.Status.FAILED,
            description=f"{desc} (Failed: {error_msg})"[:255],
            reference=request_id
        )
        return Response({"error": f"Purchase failed: {error_msg}"}, status=400)

    def _reserve_pending(self, request, amount, desc, request_id, exc):
        logger.error(f"BTDataPlug Network/Critical Failure: {exc}")
        # We genuinely don't know whether the provider processed this (timeout,
        # connection drop, etc). Reserve the funds and leave a PENDING transaction
        # so the webhook/reconcile job can settle it by client_reference.
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            if wallet.available_balance >= amount:
                wallet.available_balance -= amount
                wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=-amount,
                transaction_type=Transaction.TransactionType.BILL_PAYMENT,
                status=Transaction.Status.PENDING,
                description=f"{desc} (Pending: connection error, needs reconciliation)",
                reference=request_id
            )
        return Response({"message": "Transaction submitted. Check history for status updates."}, status=202)

class DataHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DataHistorySerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            wallet=self.request.user.wallet,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT
        ).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        # Settle this user's stuck Pending orders (missed provider callback)
        # before returning history. Never let it break the history screen.
        try:
            from .reconcile import reconcile_pending_data_orders
            reconcile_pending_data_orders(wallet=request.user.wallet, max_orders=5)
        except Exception as e:
            logger.error(f"Data history reconcile failed: {e}")
        return super().list(request, *args, **kwargs)


class DataVariationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    # Values are (network_key_for_nellobyte, display_label)
    NETWORK_MAPPING = {
        'mtn-data':    ('MTN',     'MTN'),
        'glo-data':    ('Glo',     'Glo'),
        'airtel-data': ('Airtel',  'Airtel'),
        '9mobile-data':('9mobile', '9mobile'),
    }

    _markup_cache = {}
    _plan_override_cache = None
    _disabled_plans_cache = None

    def _load_disabled_plans(self):
        if self._disabled_plans_cache is None:
            self._disabled_plans_cache = set()
            try:
                for dpp in DataPlanPrice.objects.filter(is_active=False):
                    self._disabled_plans_cache.add((dpp.network, dpp.variation_code))
            except Exception:
                pass
        return self._disabled_plans_cache

    def _load_plan_overrides(self):
        if self._plan_override_cache is None:
            self._plan_override_cache = {}
            try:
                for dpp in DataPlanPrice.objects.filter(is_active=True, selling_price__isnull=False):
                    self._plan_override_cache[(dpp.network, dpp.variation_code)] = float(dpp.selling_price)
            except Exception:
                pass
        return self._plan_override_cache

    def _get_price_factor(self, service_id):
        if service_id not in self._markup_cache:
            try:
                markup = DataMarkup.objects.get(network=service_id, is_active=True)
                self._markup_cache[service_id] = float(markup.price_factor)
            except DataMarkup.DoesNotExist:
                self._markup_cache[service_id] = 1.10
        return self._markup_cache[service_id]

    def _get_plan_field(self, plan, *keys, default=None):
        """Try multiple possible field names from the provider response."""
        for key in keys:
            val = plan.get(key)
            if val is not None:
                return val
        return default

    def _format_plan(self, plan, provider_label=None, service_id=None):
        """
        Format a normalised BTDataPlugClient plan item into the standardized response.

        Fields: PRODUCT_ID (BT DataPlug plan_id), PRODUCT_NAME, PRODUCT_AMOUNT
        Fallbacks for older / alternative field conventions are kept.
        Returns None if the plan has been disabled via DataPlanPrice.is_active=False.
        """
        variation_code = str(self._get_plan_field(
            plan,
            'PRODUCT_ID', 'ID', 'variation_code', 'id',
            default=''
        ))

        if service_id:
            disabled = self._load_disabled_plans()
            if (service_id, variation_code) in disabled:
                logger.info(f"Skipping disabled plan: {service_id}/{variation_code}")
                return None
        name = str(self._get_plan_field(
            plan,
            'PRODUCT_NAME', 'name', 'Name', 'plan_name', 'PlanName',
            default=''
        ))
        raw_price = self._get_plan_field(
            plan,
            'PRODUCT_AMOUNT',
            'price', 'Price',
            'amount', 'Amount',
            'variation_amount',
            default=0
        )
        original_price = float(str(raw_price).replace(',', ''))
        # Check per-plan override first
        overrides = self._load_plan_overrides()
        override_key = (service_id, variation_code)
        if override_key in overrides:
            selling_price = overrides[override_key]
        else:
            factor = self._get_price_factor(service_id) if service_id else 1.10
            selling_price = original_price * factor
        plan_type = str(self._get_plan_field(plan, 'type', 'Type', default='Standard'))

        formatted = {
            "variation_code": variation_code,
            "name": name,
            "variation_amount": str(round(selling_price, 2)),
            "original_amount":  str(round(original_price, 2)),
            "type": plan_type,
        }
        if provider_label:
            formatted["provider"] = provider_label
        return formatted

    def _fetch_all_raw_plans(self, client):
        """Fetch and format plans from ALL providers. Returns flat list of formatted plans."""
        all_plans = []
        for svc, (net_id, label) in self.NETWORK_MAPPING.items():
            try:
                raw = client.fetch_all_variations(net_id)
                for plan in raw:
                    try:
                        formatted = self._format_plan(plan, provider_label=label, service_id=svc)
                        if formatted is not None:
                            formatted['service_id'] = svc
                            all_plans.append(formatted)
                    except Exception as e:
                        logger.error(f"Failed to format plan for {svc}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Failed to fetch plans for {svc}: {e}")
                continue
        return all_plans

    def _fetch_single_raw_plans(self, client, service_id, network_id, provider_label):
        """Fetch and format plans for a single provider. Returns flat list."""
        raw = client.fetch_all_variations(network_id)
        formatted_plans = []
        for plan in raw:
            try:
                formatted = self._format_plan(plan, provider_label=provider_label, service_id=service_id)
                if formatted is not None:
                    formatted['service_id'] = service_id
                    formatted_plans.append(formatted)
            except Exception as e:
                logger.error(f"Failed to format plan for {provider_label}: {e}")
                continue
        return formatted_plans

    def get(self, request):
        service_id = request.query_params.get('service_id')
        client = BTDataPlugClient()

        if not service_id or service_id.lower() == 'all':
            all_plans = self._fetch_all_raw_plans(client)
        else:
            mapping = self.NETWORK_MAPPING.get(service_id)
            if not mapping:
                return Response({"error": f"Unknown service: {service_id}"}, status=400)
            network_id, provider_label = mapping
            all_plans = self._fetch_single_raw_plans(client, service_id, network_id, provider_label)

        paginator = MarketPageNumberPagination()
        paginator.page_size_query_param = 'page_size'
        page = paginator.paginate_queryset(all_plans, request)
        if page is not None:
            return paginator.get_paginated_response(page)

        return Response({"results": all_plans})


class VerifyBankAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        account_number = request.query_params.get('account_number', '').strip()
        bank_code = request.query_params.get('bank_code', '').strip()

        logger.info(f"VerifyBankAccount — account_number={account_number!r} bank_code={bank_code!r}")

        if not account_number or not bank_code:
            logger.error(f"VerifyBankAccount 400: Missing params — account_number={account_number!r} bank_code={bank_code!r}")
            return Response({
                "error": "Missing query params. Need account_number and bank_code."
            }, status=400)

        try:
            account_name, error_msg = MonnifyAPI.resolve_bank_account(account_number, bank_code)
            if account_name:
                logger.info(f"VerifyBankAccount 200: {account_name}")
                return Response({"account_name": account_name}, status=200)
            logger.error(f"VerifyBankAccount 400: {error_msg}")
            return Response({"error": error_msg}, status=400)
        except Exception as e:
            logger.error(f"VerifyBankAccount Exception: {e}")
            return Response({"error": f"Monnify says: {str(e)}"}, status=400)

class BankListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            # Call Monnify utility to get the bank list
            banks = MonnifyAPI.get_banks()
            return Response(banks, status=200)
        except Exception as e:
            logger.error(f"Failed to fetch banks: {e}")
            return Response({"error": "Could not load bank list"}, status=500)

class WithdrawalView(APIView):
    """
    User-facing: submit bank details for admin-manual payout.
    Creates a PENDING WithdrawalTicket — NO money is disbursed.
    An admin will process it offline and mark it as SUCCESSFUL/REJECTED.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        bank_code = request.data.get('bank_code')
        bank_name = request.data.get('bank_name', '')
        account_number = request.data.get('account_number')
        account_name = request.data.get('account_name', '')

        if not all([amount, bank_code, account_number]):
            return Response(
                {"error": "Missing required fields: amount, bank_code, account_number"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount_dec = Decimal(str(amount))
        except Exception:
            return Response({"error": "Invalid amount format."}, status=status.HTTP_400_BAD_REQUEST)

        if amount_dec <= 0:
            return Response(
                {"error": "Amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            if wallet.available_balance < amount_dec:
                return Response(
                    {"error": "Insufficient available balance."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ticket = WithdrawalTicket.objects.create(
                user=request.user,
                amount=amount_dec,
                bank_code=bank_code,
                bank_name=bank_name,
                account_number=account_number,
                account_name=account_name,
                status=WithdrawalTicket.StatusChoices.PENDING,
            )

        logger.info(
            "Withdrawal request created: user=%s amount=%s ticket=%s",
            request.user.id, amount_dec, ticket.id,
        )
        return Response(
            {
                "status": "pending",
                "message": "Withdrawal request submitted. An admin will process it shortly.",
                "ticket_id": ticket.id,
            },
            status=status.HTTP_201_CREATED,
        )

class AdminPendingWithdrawalListView(generics.ListAPIView):
    """Admin-only: list all pending withdrawal tickets."""
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WithdrawalTicketSerializer

    def get_queryset(self):
        return WithdrawalTicket.objects.filter(
            status=WithdrawalTicket.StatusChoices.PENDING
        ).select_related('user').order_by('-created_at')


class AdminConfirmPayoutView(APIView):
    """
    Admin-only: confirm that money has been sent to the user.
    Creates a Transaction record so the user sees it in wallet history.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, ticket_id):
        ticket = get_object_or_404(WithdrawalTicket, pk=ticket_id)

        if ticket.status != WithdrawalTicket.StatusChoices.PENDING:
            return Response(
                {"error": "Ticket already processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=ticket.user)

            if wallet.available_balance < ticket.amount:
                return Response(
                    {"error": "Insufficient balance. User funds may have been used elsewhere."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            wallet.available_balance -= ticket.amount
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=-ticket.amount,
                transaction_type=Transaction.TransactionType.WITHDRAWAL,
                status=Transaction.Status.SUCCESS,
                description=(
                    f"Withdrawal to {ticket.account_name} - "
                    f"{ticket.account_number} ({ticket.bank_name})"
                ),
            )

            ticket.status = WithdrawalTicket.StatusChoices.SUCCESSFUL
            ticket.save()

        logger.info(
            "Admin payout confirmed: ticket=%s user=%s amount=%s",
            ticket.id, ticket.user.id, ticket.amount,
        )
        return Response(
            {
                "status": "success",
                "message": "Payout confirmed. User wallet deducted.",
                "ticket_id": ticket.id,
                "amount": str(ticket.amount),
            },
            status=status.HTTP_200_OK,
        )


class DepositNotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        sender = request.data.get('sender_name')
        
        # Create a PENDING transaction record
        Transaction.objects.create(
            wallet=request.user.wallet,
            amount=amount,
            transaction_type='deposit',
            status='pending', # <--- Important
            description=f"Manual Deposit: {sender} ({request.user.username})"
        )
        # Optional: Send yourself an email or Telegram alert here!
        return Response({"message": "Admin notified"}, status=200)



@api_view(['GET', 'POST']) # Clubkonnect usually uses GET for callbacks
@permission_classes([AllowAny]) # Must be public so Clubkonnect can reach it
def clubkonnect_deposit_webhook(request):
    # Clubkonnect typically sends: orderid, statuscode, amount, and orderremark
    # The 'orderremark' usually contains the account name we set up: "NELLOBYTE-YUS (username)"
    #
    # SECURITY: Clubkonnect callbacks are not signed, so the incoming statuscode/amount
    # query params must never be trusted directly (anyone can call this URL with any
    # amount/remark). We independently requery Clubkonnect's own API for the order
    # before crediting anything, and dedupe on orderid so a replayed callback can't
    # credit twice.
    User = get_user_model()

    orderid = request.query_params.get('orderid')
    remark = request.query_params.get('orderremark', '')

    if not orderid:
        logger.warning(f"Clubkonnect deposit webhook missing orderid: {request.query_params.dict()}")
        return Response("Missing orderid", status=400)

    if Transaction.objects.filter(reference=orderid, transaction_type='deposit').exists():
        logger.info(f"Clubkonnect deposit webhook: orderid={orderid} already processed, ignoring replay")
        return Response("Already processed", status=200)

    try:
        verify_resp = NellobyteClient().query_transaction(order_id=orderid)
    except Exception as e:
        logger.error(f"Clubkonnect deposit webhook: query_transaction failed for orderid={orderid}: {e}")
        return Response("Verification request failed", status=502)

    logger.info(f"Clubkonnect deposit webhook: orderid={orderid} verify_resp={verify_resp}")

    # Be conservative: only proceed if the requery response clearly confirms success.
    # NOTE: Clubkonnect's exact field names for this query type aren't confirmed from
    # docs — the raw response is logged above so this matching can be tightened once
    # a real response has been inspected in production logs.
    status_fields = [
        str(verify_resp.get(k, '')).strip().lower()
        for k in ('status', 'orderstatus', 'ORDER_STATUS', 'statuscode')
        if isinstance(verify_resp, dict)
    ]
    is_verified_success = any(v in ('success', 'successful', 'completed', '200', '100') for v in status_fields)

    if not is_verified_success:
        logger.warning(f"Clubkonnect deposit webhook: orderid={orderid} could not be verified as successful, rejecting. Response: {verify_resp}")
        return Response("Could not verify transaction", status=400)

    verified_amount_raw = None
    for k in ('amount', 'amount_paid', 'AMOUNT', 'Amount'):
        if isinstance(verify_resp, dict) and verify_resp.get(k) is not None:
            verified_amount_raw = verify_resp.get(k)
            break

    if verified_amount_raw is None:
        logger.warning(f"Clubkonnect deposit webhook: orderid={orderid} verified but no amount found in response: {verify_resp}")
        return Response("Could not verify amount", status=400)

    try:
        verified_amount = Decimal(str(verified_amount_raw))
    except Exception:
        logger.error(f"Clubkonnect deposit webhook: orderid={orderid} unparseable amount {verified_amount_raw!r}")
        return Response("Invalid amount", status=400)

    match = re.search(r'\((.*?)\)', remark)
    if not match:
        return Response("Username not found in remark", status=400)
    username = match.group(1)

    try:
        with transaction.atomic():
            user = User.objects.get(username=username)
            wallet, _ = Wallet.objects.get_or_create(user=user)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)

            wallet.available_balance += verified_amount
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=verified_amount,
                transaction_type='deposit',
                status='success',
                reference=orderid,
                description=f"Auto-Fund: {remark}"
            )
        logger.info(f"Clubkonnect deposit webhook: credited user={username} amount={verified_amount} orderid={orderid}")
        return Response("Wallet Updated", status=200)
    except User.DoesNotExist:
        return Response(f"User {username} not found", status=404)
    except Exception as e:
        logger.error(f"Clubkonnect deposit webhook: error crediting orderid={orderid}: {e}")
        return Response(f"Error: {str(e)}", status=400)


@csrf_exempt
def btdataplug_webhook(request):
    """
    Receives BT DataPlug transaction.* events. Requests are authenticated by the
    HMAC signature, and delivery is at-least-once, so settling is idempotent.
    """
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    if not verify_webhook_signature(request.body, request.headers.get('X-BTDataPlug-Signature', '')):
        logger.warning("BTDataPlug webhook: invalid signature")
        return HttpResponse("Invalid signature", status=401)

    try:
        event = json.loads(request.body)
        order = event['data']
    except (ValueError, KeyError):
        return HttpResponse("Bad payload", status=400)

    from .reconcile import settle_from_order
    if not settle_from_order(order):
        # Unknown order or still pending -- 200 so the provider doesn't keep retrying.
        logger.info(f"BTDataPlug webhook: no state change for event={event.get('id')} ref={order.get('client_reference')}")
    return HttpResponse("OK", status=200)
