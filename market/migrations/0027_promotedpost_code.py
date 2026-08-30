import secrets

from django.db import migrations, models

_PROMO_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def _generate_promo_code(length=6):
    return ''.join(secrets.choice(_PROMO_CODE_ALPHABET) for _ in range(length))


def backfill_promo_codes(apps, schema_editor):
    PromotedPost = apps.get_model('market', 'PromotedPost')
    db_alias = schema_editor.connection.alias
    used = set(
        PromotedPost.objects.using(db_alias)
        .exclude(code='')
        .values_list('code', flat=True)
    )
    for post in PromotedPost.objects.using(db_alias).filter(code=''):
        code = _generate_promo_code()
        while code in used:
            code = _generate_promo_code()
        used.add(code)
        post.code = code
        post.save(update_fields=['code'])


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0026_promotedpost_contact_preference_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='promotedpost',
            name='code',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=12),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_promo_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='promotedpost',
            name='code',
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=12, unique=True),
        ),
    ]
