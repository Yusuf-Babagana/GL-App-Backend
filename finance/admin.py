from django.contrib import admin
import finance.models

admin.site.register(finance.models.Transaction)
admin.site.register(finance.models.Wallet)
