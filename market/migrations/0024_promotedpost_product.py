import django.db.models.deletion
from django.db import migrations, models


def clear_existing_promoted_posts(apps, schema_editor):
    # target_link had no reasonable automatic mapping to a Product FK.
    PromotedPost = apps.get_model('market', 'PromotedPost')
    PromotedPost.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0023_seed_promoted_post_pricing'),
    ]

    operations = [
        migrations.RunPython(clear_existing_promoted_posts, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='promotedpost',
            name='target_link',
        ),
        migrations.AddField(
            model_name='promotedpost',
            name='product',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='promoted_posts',
                to='market.product',
                default=1,
            ),
            preserve_default=False,
        ),
    ]
