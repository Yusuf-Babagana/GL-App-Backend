from django.contrib import admin
from .models import JobApplication, JobPosting


admin.site.register(JobApplication)
admin.site.register(JobPosting)