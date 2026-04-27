import os
import django
import uuid

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'globalink_core.settings')
django.setup()

from django.db import connection

def fix_db():
    with connection.cursor() as cursor:
        print("Starting DB fix...")
        
        # 1. Create market_shop if it doesn't exist (with UUID primary key)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_shop (
                id char(32) NOT NULL,
                name varchar(200) NOT NULL UNIQUE,
                description longtext NOT NULL,
                logo varchar(100) DEFAULT NULL,
                is_active bool NOT NULL DEFAULT 0,
                rejection_reason longtext DEFAULT NULL,
                rating decimal(3,2) NOT NULL DEFAULT 0.00,
                total_sales int NOT NULL DEFAULT 0,
                created_at datetime(6) NOT NULL,
                updated_at datetime(6) NOT NULL,
                monnify_sub_account_code varchar(100) DEFAULT NULL,
                owner_id int NOT NULL UNIQUE,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        print("✅ Shop table verified.")

        # 2. Fix market_product
        columns = [col[0] for col in connection.introspection.get_table_description(cursor, "market_product")]
        
        if 'store_id' in columns:
            cursor.execute("ALTER TABLE market_product DROP FOREIGN KEY market_product_store_id_fk_market_store_id;") # May fail if name differs
            cursor.execute("ALTER TABLE market_product DROP COLUMN store_id;")
            print("✅ Dropped store_id from product.")
            
        if 'shop_id' not in columns:
            cursor.execute("ALTER TABLE market_product ADD COLUMN shop_id char(32) NULL;")
            cursor.execute("ALTER TABLE market_product ADD CONSTRAINT fk_product_shop FOREIGN KEY (shop_id) REFERENCES market_shop(id);")
            print("✅ Added shop_id to product.")

        # 3. Fix market_order
        columns = [col[0] for col in connection.introspection.get_table_description(cursor, "market_order")]
        
        if 'store_id' in columns:
            # We try to drop it, ignore error if constraint name is unknown
            try:
                cursor.execute("ALTER TABLE market_order DROP COLUMN store_id;")
                print("✅ Dropped store_id from order.")
            except:
                print("⚠️  Manual check needed for store_id in order.")
            
        if 'shop_id' not in columns:
            cursor.execute("ALTER TABLE market_order ADD COLUMN shop_id char(32) NULL;")
            cursor.execute("ALTER TABLE market_order ADD CONSTRAINT fk_order_shop FOREIGN KEY (shop_id) REFERENCES market_shop(id);")
            print("✅ Added shop_id to order.")

        # 4. Cleanup old Store table if it exists
        cursor.execute("DROP TABLE IF EXISTS market_store;")
        print("✅ Old Store table removed.")

    print("\n🚀 Database state patched! Now run 'python manage.py migrate' to finish.")

if __name__ == "__main__":
    fix_db()
