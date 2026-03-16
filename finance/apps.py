# finance/apps.py
from django.apps import AppConfig

class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = 'Finance Management'

    def ready(self):
        # Import signals inside ready() to ensure models are fully loaded
        try:
            import finance.signals
        except ImportError:
            pass