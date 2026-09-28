from django.db import migrations


def make_product_nullable(apps, schema_editor):
    """
    Same drifted-database story as 0002/0003: the model has always
    declared Conversation.product as null=True (a conversation isn't
    necessarily about a specific product), but the actual table on
    these databases has product_id as NOT NULL. Every
    StartConversationView call that doesn't pass a product_id (i.e.
    starting a chat from a seller's profile rather than a product
    page) fails with:
        IntegrityError: NOT NULL constraint failed: chat_conversation.product_id

    A plain AlterField migration won't touch this: Django's state has
    always said null=True (0001_initial declared it that way), so it
    sees old_field == new_field and skips the real ALTER entirely -
    it only compares against recorded migration state, never the
    live DB schema. So this rebuilds the SQLite table by hand instead
    (SQLite has no direct "drop NOT NULL"), preserving data and
    indexes. Idempotent: no-op if the column is already nullable.
    """
    if schema_editor.connection.vendor != 'sqlite':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(chat_conversation)")
        # row: (cid, name, type, notnull, dflt_value, pk)
        product_col = next((row for row in cursor.fetchall() if row[1] == 'product_id'), None)

        if product_col is None or product_col[3] == 0:
            return  # already nullable, or column genuinely missing

        cursor.execute("PRAGMA foreign_keys=OFF")
        try:
            cursor.execute(
                'CREATE TABLE "chat_conversation__new" ('
                '"id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, '
                '"buyer_id" bigint NOT NULL REFERENCES "users_user" ("id") DEFERRABLE INITIALLY DEFERRED, '
                '"product_id" bigint NULL REFERENCES "market_product" ("id") DEFERRABLE INITIALLY DEFERRED, '
                '"seller_id" bigint NOT NULL REFERENCES "users_user" ("id") DEFERRABLE INITIALLY DEFERRED, '
                '"created_at" datetime NULL'
                ')'
            )
            cursor.execute(
                'INSERT INTO "chat_conversation__new" '
                '("id", "buyer_id", "product_id", "seller_id", "created_at") '
                'SELECT "id", "buyer_id", "product_id", "seller_id", "created_at" FROM "chat_conversation"'
            )
            cursor.execute('DROP TABLE "chat_conversation"')
            cursor.execute('ALTER TABLE "chat_conversation__new" RENAME TO "chat_conversation"')

            cursor.execute(
                'CREATE INDEX "chat_conversation_buyer_id_e410f8be" ON "chat_conversation" ("buyer_id")'
            )
            cursor.execute(
                'CREATE INDEX "chat_conversation_product_id_a70bba8c" ON "chat_conversation" ("product_id")'
            )
            cursor.execute(
                'CREATE INDEX "chat_conversation_seller_id_40c5e079" ON "chat_conversation" ("seller_id")'
            )
        finally:
            cursor.execute("PRAGMA foreign_keys=ON")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0029_wishlistitem'),
        ('chat', '0003_drop_conversation_updated_at'),
    ]

    operations = [
        migrations.RunPython(make_product_nullable, noop_reverse),
    ]
