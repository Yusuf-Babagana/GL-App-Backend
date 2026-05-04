from django.db import migrations


def add_pending_balance(apps, schema_editor):
    """Add pending_balance column only if it doesn't already exist."""
    with schema_editor.connection.cursor() as cursor:
        # Check if the column already exists
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'finance_wallet'
              AND COLUMN_NAME = 'pending_balance'
        """)
        exists = cursor.fetchone()[0]

        if not exists:
            cursor.execute("""
                ALTER TABLE finance_wallet
                ADD COLUMN pending_balance DECIMAL(12, 2) NOT NULL DEFAULT 0.00
            """)


def remove_pending_balance(apps, schema_editor):
    """Reverse: drop the column if it exists."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'finance_wallet'
              AND COLUMN_NAME = 'pending_balance'
        """)
        exists = cursor.fetchone()[0]

        if exists:
            cursor.execute("""
                ALTER TABLE finance_wallet DROP COLUMN pending_balance
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_alter_transaction_transaction_type_and_more'),
    ]

    operations = [
        migrations.RunPython(add_pending_balance, remove_pending_balance),
    ]
