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
        print(f"WEBHOOK RECEIVED: {event_type}")
        
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
            Transaction.objects.filter(reference=ref).update(status=Transaction.Status.SUCCESS)
            logger.info(f"✅ Disbursement successful for ref {ref}")
            return Response({"status": "success"}, status=status.HTTP_200_OK)

        elif event_type == 'DISBURSEMENT_FAILED':
            ref = event_data.get('reference')
            try:
                with transaction.atomic():
                    ledger = Transaction.objects.select_for_update().get(reference=ref)
                    # Only refund if the wallet was actually deducted (SUCCESS status).
                    # PENDING transactions haven't deducted the wallet yet.
                    if ledger.status == Transaction.Status.SUCCESS:
                        ledger.wallet.available_balance += abs(ledger.amount)
                        ledger.wallet.save()
                        ledger.status = Transaction.Status.FAILED
                        ledger.description += " (Failed: Refunded)"
                        ledger.save()
                        logger.warning(f"⚠️ Disbursement failed and refunded for ref {ref}")
                    else:
                        ledger.status = Transaction.Status.FAILED
                        ledger.save(update_fields=['status'])
                        logger.warning(f"⚠️ Disbursement failed for ref {ref} (was PENDING, no refund needed)")
            except Exception as e:
                logger.error(f"❌ Webhook Refund failure: {e}")

        return Response({"status": "success"}, status=200)


from .nellobyte import NellobyteClient
from market.pagination import MarketPageNumberPagination

class DataPurchaseView(APIView):
    """
    Handles Data Bundle purchases using NellobyteClient.
    Fetches the live price from Nellobyte + admin markup on the server.
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

        client = NellobyteClient()
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

        # Fetch live price from Nellobyte + admin markup
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

        # Call Nellobyte FIRST before touching wallet
        try:
            client = NellobyteClient()
            logger.info(f"Calling Nellobyte with req_id={request_id}, svc={service_id}, plan={data_plan}, ph={phone}")
            resp = client.purchase_data(request_id, service_id, data_plan, phone)

            status_code = str(resp.get('statuscode'))
            order_status = resp.get('status', '')

            if status_code == '100':
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
                        status=Transaction.Status.SUCCESS,
                        description=f"Nellobyte Data: {service_id.upper()} ({data_plan}) to {phone}",
                        reference=resp.get('orderid', request_id)
                    )

                return Response({
                    "message": "Data purchase successful!",
                    "order_id": resp.get('orderid'),
                    "new_balance": float(wallet.available_balance)
                }, status=200)

            elif 'ORDER_RECEIVED' in order_status or status_code in ('', '101', '102'):
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
                        status=Transaction.Status.PENDING,
                        description=f"Nellobyte Data: {service_id.upper()} ({data_plan}) to {phone} (Pending)",
                        reference=resp.get('orderid', request_id)
                    )

                logger.info(f"Data Purchase 202: Order queued — orderid={resp.get('orderid')} status={order_status}")
                return Response({
                    "message": "Order submitted for processing. Check history for status updates.",
                    "order_id": resp.get('orderid'),
                    "new_balance": float(wallet.available_balance)
                }, status=202)

            else:
                error_msg = resp.get('status', 'Provider rejected request')
                with transaction.atomic():
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=0,
                        transaction_type=Transaction.TransactionType.BILL_PAYMENT,
                        status=Transaction.Status.FAILED,
                        description=f"Nellobyte Data: {service_id.upper()} ({data_plan}) to {phone} (Failed: {error_msg})",
                        reference=resp.get('orderid', request_id)
                    )

                logger.error(f"Data Purchase 400: Nellobyte Error: {error_msg} | Code: {status_code} | Raw: {resp}")
                return Response({"error": f"Nellobyte Error: {error_msg}"}, status=400)

        except Exception as e:
            logger.error(f"Nellobyte Network/Critical Failure: {e}")
            return Response({"message": "Transaction submitted. Check history for status updates."}, status=202)

class DataHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DataHistorySerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            wallet=self.request.user.wallet,
            transaction_type=Transaction.TransactionType.BILL_PAYMENT
        ).order_by('-created_at')


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
        """Try multiple possible field names from Nellobyte response."""
        for key in keys:
            val = plan.get(key)
            if val is not None:
                return val
        return default

    def _format_plan(self, plan, provider_label=None, service_id=None):
        """
        Format a raw Nellobyte V2 PRODUCT item into the standardized response.

        Nellobyte V2 fields:  PRODUCT_ID, PRODUCT_NAME, PRODUCT_AMOUNT, PRODUCT_CODE
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
        client = NellobyteClient()

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
        # 1. Log what we received
        print(f"DEBUG: Params received from App: {request.query_params}")
        
        account_number = request.query_params.get('account_number')
        bank_code = request.query_params.get('bank_code')

        if not account_number or not bank_code:
            return Response({
                "error": f"Missing query params. Need account_number and bank_code."
            }, status=400)

        try:
            # 2. Call the service and catch the specific error
            account_name, error_msg = MonnifyAPI.resolve_bank_account(account_number, bank_code)
            if account_name:
                return Response({"account_name": account_name}, status=200)
            return Response({"error": error_msg}, status=400)
        except Exception as e:
            # 3. Print the EXACT error from Monnify to the console
            print(f"🚨 MONNIFY API FAILURE: {str(e)}")
            # 4. Return the ACTUAL error to your React Native app
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
    User = get_user_model()
    
    remark = request.query_params.get('orderremark', '')
    amount = request.query_params.get('amount', 0)
    status_code = request.query_params.get('statuscode')

    if status_code == '200': # 200 usually means success in their callbacks
        # 1. Extract username from the remark "NELLOBYTE-YUS (username)"
        try:
            match = re.search(r'\((.*?)\)', remark)
            if not match:
                return Response("Username not found in remark", status=400)
            
            username = match.group(1)
            
            # 2. Find the user and their wallet
            user = User.objects.get(username=username)
            wallet, _ = Wallet.objects.get_or_create(user=user)
            
            # 3. Credit the wallet
            wallet.available_balance += Decimal(str(amount))
            wallet.save()
            
            # 4. Record the transaction
            Transaction.objects.create(
                wallet=wallet, 
                amount=Decimal(str(amount)), 
                transaction_type='deposit', 
                status='success',
                description=f"Auto-Fund: {remark}"
            )
            return Response("Wallet Updated", status=200)
        except User.DoesNotExist:
            return Response(f"User {username} not found", status=404)
        except Exception as e:
            return Response(f"Error: {str(e)}", status=400)

    return Response("Invalid Status", status=400)


@csrf_exempt
def webhook_data_callback(request):
    orderid = request.GET.get('orderid')
    statuscode = request.GET.get('statuscode')
    orderstatus = request.GET.get('orderstatus', '')
    orderremark = request.GET.get('orderremark', '')

    logger.info(f"Nellobyte callback: orderid={orderid} statuscode={statuscode} orderstatus={orderstatus} orderremark={orderremark}")

    if not orderid or not statuscode:
        return HttpResponse("Missing orderid or statuscode", status=400)

    try:
        txn = Transaction.objects.get(reference=orderid, transaction_type=Transaction.TransactionType.BILL_PAYMENT)
    except Transaction.DoesNotExist:
        logger.error(f"Nellobyte callback: Transaction not found for orderid={orderid}")
        return HttpResponse("Transaction not found", status=404)

    with transaction.atomic():
        txn = Transaction.objects.select_for_update().get(pk=txn.pk)

        if orderremark:
            txn.description = (txn.description or '') + f" | Remark: {orderremark}"

        # Some Nellobyte callbacks return non-100 codes even when the
        # data was successfully delivered (e.g. "successfully sold").
        # Check the remark text — if it indicates success, honour it.
        remark_lower = (orderremark or '').lower()
        succeeded = any(kw in remark_lower for kw in ['successfully sold', 'successful', 'completed successfully'])

        if statuscode == '100' or succeeded:
            txn.status = Transaction.Status.SUCCESS
            txn.description += f" (Completed: code={statuscode})"
            txn.save()
            logger.info(f"Nellobyte callback: Transaction {txn.id} marked SUCCESS (orderid={orderid})")
            return HttpResponse("OK", status=200)
        else:
            txn.status = Transaction.Status.FAILED
            txn.description += f" (Failed: code={statuscode})"
            if txn.amount < 0 and 'Refunded' not in txn.description:
                wallet = Wallet.objects.select_for_update().get(pk=txn.wallet_id)
                wallet.available_balance += abs(txn.amount)
                wallet.save()
                txn.description += " (Wallet Refunded)"
            txn.save()

            # Auto-disable plans that fail with provider-side errors
            if any(kw in remark_lower for kw in ['no active sim', 'inactive sim', 'not have an active sim']):
                match = re.search(r'([A-Z]+-DATA)\s*\(([^)]+)\)', txn.description)
                if match:
                    raw_service = match.group(1).lower()
                    variation_code = match.group(2)
                    service_map = {
                        'mtn-data': 'mtn-data',
                        'glo-data': 'glo-data',
                        '9mobile-data': '9mobile-data',
                        'airtel-data': 'airtel-data',
                    }
                    service_id = service_map.get(raw_service)
                    if service_id:
                        DataPlanPrice.objects.update_or_create(
                            network=service_id,
                            variation_code=variation_code,
                            defaults={'is_active': False, 'plan_name': f'Auto-disabled: {orderremark}'}
                        )
                        logger.info(f"Auto-disabled plan {service_id}/{variation_code} due to provider error")

            logger.warning(f"Nellobyte callback: Transaction {txn.id} marked FAILED (orderid={orderid}, code={statuscode})")
            return HttpResponse("OK", status=200)
