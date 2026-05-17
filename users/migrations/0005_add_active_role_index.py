from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_user_transaction_pin'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='active_role',
            field=models.CharField(
                choices=[
                    ('buyer', 'Buyer'), ('seller', 'Seller'),
                    ('job_seeker', 'Job Seeker'), ('employer', 'Employer'),
                    ('delivery_partner', 'Delivery Partner'), ('admin', 'Admin'),
                ],
                db_index=True, default='buyer', max_length=20,
            ),
        ),
    ]
