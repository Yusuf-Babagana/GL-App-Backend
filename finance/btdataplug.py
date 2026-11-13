import hashlib
import hmac
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class BTDataPlugError(Exception):
    """Raised when BT DataPlug returns an error envelope or cannot be reached."""

    def __init__(self, message, code=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class BTDataPlugClient:
    # Maps the app's service ids to the network names the API expects
    NETWORK_NAMES = {
        'mtn-data': 'MTN',
        'glo-data': 'GLO',
        'airtel-data': 'AIRTEL',
        '9mobile-data': '9MOBILE',
    }
    # Maps the app-friendly network key used by the views to the API network name
    NETWORK_KEY_MAP = {
        'MTN': 'MTN',
        'Glo': 'GLO',
        'Airtel': 'AIRTEL',
        '9mobile': '9MOBILE',
    }

    def __init__(self):
        self.base_url = getattr(settings, 'BTDATAPLUG_BASE_URL', 'https://www.btdataplug.com/api/v1/dev').rstrip('/')
        self.api_key = settings.BTDATAPLUG_API_KEY
        self.secret_key = settings.BTDATAPLUG_SECRET_KEY

    def _headers(self, idempotency_key=None):
        headers = {
            'X-API-Key': self.api_key,
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        return headers

    def _request(self, method, path, params=None, json=None, idempotency_key=None, timeout=30):
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, params=params, json=json,
            headers=self._headers(idempotency_key), timeout=timeout,
        )
        try:
            body = resp.json()
        except ValueError:
            raise BTDataPlugError(f"Non-JSON response (HTTP {resp.status_code})", http_status=resp.status_code)

        if not body.get('success'):
            err = body.get('error') or {}
            raise BTDataPlugError(
                err.get('message', 'Provider error'),
                code=err.get('code'),
                http_status=resp.status_code,
            )
        return body

    def fetch_all_variations(self, network_key):
        """
        Returns the plans for one network (network_key: 'MTN', 'Glo', 'Airtel', '9mobile').

        Each item is normalised to the PRODUCT_* keys the views already read:
        PRODUCT_ID (BT DataPlug plan_id), PRODUCT_NAME, PRODUCT_AMOUNT.
        """
        network = self.NETWORK_KEY_MAP.get(network_key, network_key)
        try:
            body = self._request('GET', '/data-plans/', params={'network': network}, timeout=20)
        except Exception as e:
            logger.error(f"[BTDataPlug] fetch_all_variations error for '{network_key}': {e}")
            return []

        plans = (body.get('data') or {}).get('plans', [])
        return [
            {
                'PRODUCT_ID': str(p['plan_id']),
                'PRODUCT_NAME': p.get('name', ''),
                'PRODUCT_AMOUNT': p.get('price', '0'),
            }
            for p in plans
        ]

    def _purchase(self, path, payload, request_id):
        """
        POSTs an order. request_id doubles as the idempotency key and client_reference,
        so retrying a timed-out purchase with the same request_id never double-charges.

        Returns the order dict (reference, status, failure_reason, result, ...). Raises
        BTDataPlugError on rejection; a 'purchase_failed' error means the wallet was
        refunded by the provider.
        """
        payload = {**payload, 'client_reference': request_id}
        logger.info(f"BTDataPlug POST {path} — payload={payload}")
        body = self._request('POST', path, json=payload, idempotency_key=request_id)
        logger.info(f"BTDataPlug POST {path} response — {body}")
        return body['data']

    def purchase_data(self, request_id, plan_id, phone):
        return self._purchase('/data/', {'plan_id': int(plan_id), 'phone': phone}, request_id)

    def purchase_airtime(self, request_id, network, phone, amount):
        return self._purchase('/airtime/', {'network': network, 'phone': phone, 'amount': str(amount)}, request_id)

    def purchase_electricity(self, request_id, disco, meter_no, meter_type, amount, phone):
        return self._purchase('/electricity/', {
            'disco': disco, 'meter_no': meter_no, 'meter_type': meter_type,
            'amount': str(amount), 'phone': phone,
        }, request_id)

    def purchase_cable(self, request_id, cable_tv, package_id, smartcard, phone):
        return self._purchase('/cable/', {
            'cable_tv': cable_tv, 'package_id': package_id, 'smartcard': smartcard, 'phone': phone,
        }, request_id)

    def get_discos(self):
        """{'discos': [{code, name}], 'meter_types': [...], 'minimum_amount': '1000.00', 'service_fee': '100.00'}"""
        return self._request('GET', '/electricity/discos/', timeout=20)['data']

    def get_cable_plans(self, cable_tv):
        """[{'package_id', 'cable_tv', 'name', 'price'}]"""
        return self._request('GET', '/cable-plans/', params={'cable_tv': cable_tv}, timeout=20)['data']['plans']

    def verify_meter(self, disco, meter_no, meter_type):
        return self._request('GET', '/verify/meter/', params={
            'disco': disco, 'meter_no': meter_no, 'meter_type': meter_type,
        }, timeout=30)['data']

    def verify_cable(self, cable_tv, smartcard):
        return self._request('GET', '/verify/cable/', params={
            'cable_tv': cable_tv, 'smartcard': smartcard,
        }, timeout=30)['data']

    def query_transaction(self, reference=None, client_reference=None):
        """Source of truth for an order's status. Returns the order dict, or None if unknown."""
        if reference:
            return self._request('GET', f'/transactions/{reference}/')['data']
        body = self._request('GET', '/transactions/', params={'client_reference': client_reference})
        data = body.get('data') or {}
        results = data.get('transactions') or data.get('results') or (data if isinstance(data, list) else [])
        return results[0] if results else None

    def get_balance(self):
        return self._request('GET', '/balance/')['data']


def verify_webhook_signature(raw_body, signature_header, tolerance_seconds=300):
    """Checks X-BTDataPlug-Signature: t=<unix>,v1=<hex> (HMAC-SHA256 over t + '.' + raw body)."""
    secret = getattr(settings, 'BTDATAPLUG_WEBHOOK_SECRET', '')
    if not secret or not signature_header:
        return False
    try:
        parts = dict(item.split('=', 1) for item in signature_header.split(','))
        timestamp, signature = parts['t'], parts['v1']
        if abs(time.time() - int(timestamp)) > tolerance_seconds:
            return False
    except (KeyError, ValueError):
        return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# Problems on OUR side of the provider relationship (wallet, keys, approval, IP list,
# daily limit). The user did nothing wrong and can't fix them, so they get a generic
# message and the admins are emailed.
PROVIDER_SIDE_CODES = {
    'insufficient_funds', 'application_pending', 'application_suspended', 'ip_not_allowed',
    'service_not_permitted', 'missing_credentials', 'invalid_credentials',
    'daily_limit_reached', 'too_many_failed_attempts', 'rate_limited',
}
GENERIC_UNAVAILABLE = "Service temporarily unavailable. Please try again later."


def is_definite_rejection(exc):
    """
    True when the provider clearly did NOT process the order, so charging the user would be
    wrong. Every 4xx answer means the request was refused before any purchase happened, except
    409 request_in_progress (the original may still complete). 503 service_unavailable is also a
    refusal. Timeouts, connection drops and 5xx are unclear: the order may have gone through.
    """
    if getattr(exc, 'code', None) == 'request_in_progress':
        return False
    if exc.code == 'service_unavailable':
        return True
    return exc.http_status is not None and 400 <= exc.http_status < 500


def user_message(exc):
    return GENERIC_UNAVAILABLE if exc.code in PROVIDER_SIDE_CODES else str(exc)


def alert_if_provider_side(exc):
    """Email the admins (at most once an hour per problem) when the cause is on our side."""
    if exc.code not in PROVIDER_SIDE_CODES:
        return
    logger.critical("BT DataPlug refused an order for a reason on our side: %s (%s)", exc, exc.code)
    from django.core.cache import cache
    from globalink_core.notify import notify_admins
    if cache.add(f"btd-alert-{exc.code}", 1, 3600):
        notify_admins(
            "Purchases are failing: BT DataPlug problem",
            f"BT DataPlug refused a customer purchase.\n\nCode: {exc.code}\nMessage: {exc}\n\n"
            "Customers see 'Service temporarily unavailable' until this is fixed. Typical causes: the "
            "BT DataPlug wallet is empty (fund it), the application is not approved or was suspended, "
            "the API keys were regenerated, or this server's IP is not on the allowed list.",
        )
