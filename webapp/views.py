"""
Web client for GLAPP.

A single-page app that talks to the existing REST API (/api/...) with the same
JWT flow the mobile app uses. This module adds no models, endpoints or
behaviour to the API itself -- it only serves the static shell + assets, so it
cannot affect the mobile app or the admin portal.

Assets are streamed straight from webapp/assets so deployment does not depend
on `collectstatic` being re-run.
"""
import mimetypes
import os

from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
ALLOWED_ASSETS = {
    'app.css', 'favicon.svg', 'i18n.js', 'logo.jpeg',
    'core.js', 'pages_shop.js', 'pages_money.js', 'pages_account.js', 'pages_seller.js', 'pages_misc.js', 'boot.js',
}


@require_GET
@never_cache
def index(request):
    with open(os.path.join(ASSET_DIR, 'index.html'), 'rb') as fh:
        return HttpResponse(fh.read(), content_type='text/html; charset=utf-8')


@require_GET
def asset(request, name):
    if name not in ALLOWED_ASSETS:
        raise Http404
    path = os.path.join(ASSET_DIR, name)
    if not os.path.isfile(path):
        raise Http404
    ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    resp = FileResponse(open(path, 'rb'), content_type=ctype)
    resp['Cache-Control'] = 'no-cache'
    return resp
