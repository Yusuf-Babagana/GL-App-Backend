from django.db import migrations


class Migration(migrations.Migration):
    """
    Adds pending_balance to the Wallet table using raw SQL.
    This bypasses dependency chain issues between environments.
    Safe to run even if the column already exists (IF NOT EXISTS guard).
    """

    # Intentionally empty — doesn't depend on any previous migration
    # so it works regardless of what's already applied on the server.
    dependencies = [
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            # Forward: Add the column if it doesn't already exist
            sql="""
                ALTER TABLE finance_wallet
                ADD COLUMN IF NOT EXISTS pending_balance
                DECIMAL(12, 2) NOT NULL DEFAULT 0.00;
            """,
            # Reverse: Drop the column on rollback
            reverse_sql="""
                ALTER TABLE finance_wallet
                DROP COLUMN IF EXISTS pending_balance;
            """,
        ),
    ]
