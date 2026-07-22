from decimal import Decimal
from django.db import migrations


def seed_default_pricing(apps, schema_editor):
    PromotedPostPricing = apps.get_model('market', 'PromotedPostPricing')
    defaults = [
        ('24h', Decimal('1000.00')),
        ('3days', Decimal('2000.00')),
        ('1wk', Decimal('4000.00')),
    ]
    for duration_type, price in defaults:
        PromotedPostPricing.objects.get_or_create(
            duration_type=duration_type,
            defaults={'price': price, 'is_active': True},
        )


def reverse_seed(apps, schema_editor):
    PromotedPostPricing = apps.get_model('market', 'PromotedPostPricing')
    PromotedPostPricing.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0022_promotedpostpricing'),
    ]

    operations = [
        migrations.RunPython(seed_default_pricing, reverse_seed),
    ]
