from django.db import migrations


def add_missing_created_at(apps, schema_editor):
    """
    Some databases have a chat_conversation table that predates the
    current model/migration history and never actually got a
    created_at column (it has an orphaned updated_at column instead,
    which nothing in the codebase reads). 0001_initial's CreateModel
    assumes the column already exists, so on those databases every
    query on Conversation crashes with "no such column:
    chat_conversation.created_at" (its Meta.ordering uses it).

    This repairs the schema without touching data: idempotent (skips
    databases that already have the column, i.e. anything created
    fresh from the current migrations), and backfills from the old
    updated_at column when present so existing rows keep a sensible
    timestamp instead of NULL.
    """
    if schema_editor.connection.vendor != 'sqlite':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(chat_conversation)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'created_at' in columns:
            return

        cursor.execute("ALTER TABLE chat_conversation ADD COLUMN created_at datetime NULL")

        if 'updated_at' in columns:
            cursor.execute(
                "UPDATE chat_conversation SET created_at = updated_at WHERE created_at IS NULL"
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_missing_created_at, noop_reverse),
    ]
