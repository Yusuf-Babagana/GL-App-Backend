from django.core.management.base import BaseCommand
from django.db import connection


OLD_TABLES = [
    'chat_conversation_participants',
    'market_conversation',
    'market_message',
]

ALL_MIGRATIONS = {
    'admin': ['0001_initial', '0002_logentry_remove_auto_add', '0003_logentry_add_action_flag_choices',
              '0004_alter_logentry_action_flag_choices'],
    'auth': ['0001_initial', '0002_alter_permission_name_max_length', '0003_alter_user_email_max_length',
             '0004_alter_user_username_opts', '0005_alter_user_last_login_null', '0006_require_contenttypes_0002',
             '0007_alter_validators_add_error_messages', '0008_alter_user_username_max_length',
             '0009_alter_user_last_name_max_length', '0010_alter_group_name_max_length',
             '0011_update_proxy_permissions', '0012_alter_user_first_name_max_length'],
    'authtoken': ['0001_initial', '0002_auto_20160226_1747', '0003_tokenproxy', '0004_alter_tokenproxy_options'],
    'chat': ['0001_initial'],
    'contenttypes': ['0001_initial', '0002_remove_content_type_name'],
    'finance': ['0001_initial', '0002_wallet_account_number_wallet_account_reference_and_more',
                '0003_alter_transaction_transaction_type_and_more', '0004_add_pending_balance_to_wallet',
                '0005_remove_bankaccount_is_primary_and_more', '0008_merge_rename_and_platform'],
    'jobs': ['0001_initial', '0002_initial'],
    'logistics': ['0001_initial', '0002_initial'],
    'market': ['0001_initial', '0002_rename_delivery_partner_order_rider_and_more',
               '0003_conversation_message', '0004_alter_productimage_image', '0005_store_is_verified',
               '0006_product_is_ad', '0007_alter_conversation_participants', '0008_product_image',
               '0009_order_monnify_reference_and_more', '0010_merchantprofile_shop_remove_order_store_and_more',
               '0011_remove_message_conversation_remove_message_sender_and_more',
               '0012_alter_product_price_alter_shop_is_active_and_more',
               '0013_shop_business_phone_shop_country_shop_date_applied_and_more',
               '0014_alter_order_payment_status', '0015_alter_product_video_alter_shop_logo',
               '0016_product_video_ad_url', '0017_alter_product_category'],
    'sessions': ['0001_initial'],
    'users': ['0001_initial', '0002_address_last_seen_user_is_online_user_push_token',
              '0003_user_last_seen', '0004_user_transaction_pin', '0005_add_active_role_index',
              '0006_alter_user_managers_user_bvn_user_nin'],
}


class Command(BaseCommand):
    help = 'Fixes migration graph corruption: drops old tables, ensures chat tables, fakes all migrations'

    def handle(self, *args, **options):
        self.drop_old_tables()
        self.ensure_chat_tables()
        self.fake_all_migrations()
        self.remove_orphaned_entries()
        self.stdout.write(self.style.SUCCESS('Migration state is now consistent. Run: python manage.py migrate'))

    def drop_old_tables(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {row[0] for row in cursor.fetchall()}
        for table in OLD_TABLES:
            if table in existing:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
                self.stdout.write(self.style.WARNING(f'Dropped old table: {table}'))
            else:
                self.stdout.write(f'Table {table} not found, skipping')

    def ensure_chat_tables(self):
        with connection.cursor() as cursor:
            cursor.executescript("""
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
                CREATE INDEX IF NOT EXISTS "chat_conversation_buyer_id_e410f8be" ON "chat_conversation" ("buyer_id");
                CREATE INDEX IF NOT EXISTS "chat_conversation_product_id_a70bba8c" ON "chat_conversation" ("product_id");
                CREATE INDEX IF NOT EXISTS "chat_conversation_seller_id_40c5e079" ON "chat_conversation" ("seller_id");
                CREATE INDEX IF NOT EXISTS "chat_message_created_at_618078f0" ON "chat_message" ("created_at");
                CREATE INDEX IF NOT EXISTS "chat_message_conversation_id_a1207bf4" ON "chat_message" ("conversation_id");
                CREATE INDEX IF NOT EXISTS "chat_message_sender_id_991c686c" ON "chat_message" ("sender_id");
            """)
        self.stdout.write(self.style.SUCCESS('Chat tables ensured'))

    def fake_all_migrations(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations")
            existing = {(row[0], row[1]) for row in cursor.fetchall()}

        total = 0
        for app, names in ALL_MIGRATIONS.items():
            for name in names:
                if (app, name) not in existing:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, datetime('now'))",
                            [app, name],
                        )
                    total += 1

        if total:
            self.stdout.write(self.style.SUCCESS(f'Faked {total} missing migration(s)'))
        else:
            self.stdout.write('All migrations already registered')

    def remove_orphaned_entries(self):
        registered = {}
        for app, names in ALL_MIGRATIONS.items():
            for name in names:
                registered[(app, name)] = True

        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations")
            for row in cursor.fetchall():
                key = (row[0], row[1])
                if key not in registered:
                    cursor.execute(
                        "DELETE FROM django_migrations WHERE app=%s AND name=%s",
                        [row[0], row[1]],
                    )
                    self.stdout.write(self.style.WARNING(f'Removed orphaned migration: {row[0]}.{row[1]}'))
