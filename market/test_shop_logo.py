import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import override_settings

from .serializers import resolve_logo_url
from .test_escrow import Base

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, MEDIA_URL='/media/')
class ShopLogoTests(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def logo_in_api(self, value):
        self.shop.logo = value
        self.shop.save()
        r = self.b.get("/api/market/stores/")
        rows = r.json().get('results', r.json())
        return next(x for x in rows if x['id'] == str(self.shop.pk))['logo']

    def test_empty_and_junk_values_mean_no_logo(self):
        for v in (None, "", "None", "null", "undefined", "  "):
            self.assertIsNone(self.logo_in_api(v), v)

    def test_full_url_is_passed_through(self):
        url = "https://res.cloudinary.com/x/image/upload/v1/a.png"
        self.assertEqual(self.logo_in_api(url), url)

    def test_media_relative_path_becomes_absolute_without_double_media(self):
        default_storage.save("shop_logos/a.png", ContentFile(b"x"))
        got = self.logo_in_api("/media/shop_logos/a.png")
        self.assertTrue(got.startswith("http"), got)
        self.assertTrue(got.endswith("/media/shop_logos/a.png"), got)
        self.assertNotIn("/media/media/", got)

    def test_bare_filename_resolves_only_if_the_file_exists(self):
        default_storage.save("legacy.jpeg", ContentFile(b"x"))
        self.assertTrue(self.logo_in_api("legacy.jpeg").endswith("/media/legacy.jpeg"))
        # The legacy rows in production point at files that are gone: no logo, not a 404 URL.
        self.assertIsNone(self.logo_in_api("missing.jpeg"))

    def test_resolver_never_raises_on_odd_input(self):
        self.assertIsNone(resolve_logo_url("../../etc/passwd"))
