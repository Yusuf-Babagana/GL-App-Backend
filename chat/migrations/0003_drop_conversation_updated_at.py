from django.db import migrations


def drop_orphaned_updated_at(apps, schema_editor):
    """
    The same drifted databases fixed by 0002 also have updated_at
    declared NOT NULL with no default. Nothing in the codebase reads
    or writes that column - it's not a model field - so every
    Conversation.objects.create(...) (i.e. every new chat a buyer
    starts with a seller) fails with:
        IntegrityError: NOT NULL constraint failed: chat_conversation.updated_at

    SQLite (3.35+) supports DROP COLUMN directly, so just remove the
    dead column. Idempotent: no-op on a database that doesn't have it.
    """
    if schema_editor.connection.vendor != 'sqlite':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(chat_conversation)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'updated_at' not in columns:
            return

        cursor.execute("ALTER TABLE chat_conversation DROP COLUMN updated_at")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_fix_conversation_created_at_drift'),
    ]

    operations = [
        migrations.RunPython(drop_orphaned_updated_at, noop_reverse),
    ]
