from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    replaces = [
        ('finance', '0006_rename_balance_fields'),
        ('finance', '0007_platformrevenue_withdrawalticket_and_more'),
    ]

    dependencies = [
        ('finance', '0005_remove_bankaccount_is_primary_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
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
        migrations.CreateModel(
            name='PlatformRevenue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_commission', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Platform revenues',
            },
        ),
        migrations.CreateModel(
            name='WithdrawalTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('bank_code', models.CharField(max_length=3)),
                ('bank_name', models.CharField(max_length=255)),
                ('account_number', models.CharField(max_length=10)),
                ('account_name', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('SUCCESSFUL', 'Successful'), ('REJECTED', 'Rejected')], default='PENDING', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='withdrawal_tickets', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.DeleteModel(
            name='WithdrawalRequest',
        ),
    ]
