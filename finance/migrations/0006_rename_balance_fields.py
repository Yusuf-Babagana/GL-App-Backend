from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_remove_bankaccount_is_primary_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='wallet',
            old_name='balance',
            new_name='available_balance',
        ),
        migrations.RenameField(
            model_name='wallet',
            old_name='pending_balance',
            new_name='locked_balance',
        ),
    ]
