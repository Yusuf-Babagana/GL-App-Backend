from django.db import migrations, models


class Migration(migrations.Migration):
    """
    SAFE migration: Only adds pending_balance to Wallet.
    Avoids touching BankAccount fields to prevent errors on PythonAnywhere.
    """

    dependencies = [
        ('finance', '0003_alter_transaction_transaction_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='pending_balance',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=12),
        ),
    ]
