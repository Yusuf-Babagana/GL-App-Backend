from django.core.management.base import BaseCommand
from django.db import connection


SQL = """
CREATE TABLE IF NOT EXISTS "chat_conversation" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "buyer_id" bigint NOT NULL REFERENCES "users_user" ("id") DEFERRABLE INITIALLY DEFERRED,
    "product_id" bigint NULL REFERENCES "market_product" ("id") DEFERRABLE INITIALLY DEFERRED,
    "seller_id" bigint NOT NULL REFERENCES "users_user" ("id") DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS "chat_message" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "text" text NOT NULL,
    "is_read" bool NOT NULL,
    "created_at" datetime NOT NULL,
    "conversation_id" bigint NOT NULL REFERENCES "chat_conversation" ("id") DEFERRABLE INITIALLY DEFERRED,
    "sender_id" bigint NOT NULL REFERENCES "users_user" ("id") DEFERRABLE INITIALLY DEFERRED
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS "chat_conversation_buyer_id_e410f8be" ON "chat_conversation" ("buyer_id");
CREATE INDEX IF NOT EXISTS "chat_conversation_product_id_a70bba8c" ON "chat_conversation" ("product_id");
CREATE INDEX IF NOT EXISTS "chat_conversation_seller_id_40c5e079" ON "chat_conversation" ("seller_id");
CREATE INDEX IF NOT EXISTS "chat_message_created_at_618078f0" ON "chat_message" ("created_at");
CREATE INDEX IF NOT EXISTS "chat_message_conversation_id_a1207bf4" ON "chat_message" ("conversation_id");
CREATE INDEX IF NOT EXISTS "chat_message_sender_id_991c686c" ON "chat_message" ("sender_id");
"""


class Command(BaseCommand):
    help = 'Creates chat tables if they do not exist'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.executescript(SQL)
            cursor.executescript(INDEXES)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM django_migrations WHERE app='chat' AND name='0001_initial'"
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO django_migrations (app, name, applied) VALUES ('chat', '0001_initial', datetime('now'))"
                )
                self.stdout.write(self.style.SUCCESS('Registered chat 0001_initial migration'))
            else:
                self.stdout.write('Migration already registered')

        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM django_migrations WHERE app='finance' AND name IN ('0006_rename_balance_fields', '0007_platformrevenue_withdrawalticket_and_more')"
            )
            if cursor.rowcount:
                self.stdout.write(self.style.WARNING(f'Cleaned {cursor.rowcount} orphaned finance migration(s)'))

        self.stdout.write(self.style.SUCCESS('Chat tables ready'))
