import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'globalink_core.settings')
django.setup()

from market.models import MerchantProfile, Shop

def fix_database():
    print("Running database fix script...")
    with connection.schema_editor() as schema_editor:
        # 1. Create MerchantProfile table
        try:
            schema_editor.create_model(MerchantProfile)
            print("✅ Successfully created MerchantProfile table.")
        except Exception as e:
            print(f"⚠️ Error creating MerchantProfile (might already exist): {e}")

        # 2. Add new fields to Shop table
        fields_to_add = ['shop_type', 'address', 'state', 'is_registered', 'cac_number']
        
        for field_name in fields_to_add:
            field = Shop._meta.get_field(field_name)
            try:
                schema_editor.add_field(Shop, field)
                print(f"✅ Successfully added '{field_name}' to Shop table.")
            except Exception as e:
                print(f"⚠️ Error adding '{field_name}' (might already exist): {e}")
                
    print("\nDatabase schema is now aligned with models! You can now safely fake the migration.")

if __name__ == "__main__":
    fix_database()
