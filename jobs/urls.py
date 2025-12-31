from django.urls import path
from .views import (
    JobListView, JobDetailView, SeekerProfileView, 
    ApplyJobView, EmployerApplicationsView
)

urlpatterns = [
    # Public & Employer
    path('list/', JobListView.as_view(), name='job-list'), # GET (All), POST (Create)
    path('<int:pk>/', JobDetailView.as_view(), name='job-detail'),

    # Seeker
    path('profile/me/', SeekerProfileView.as_view(), name='seeker-profile'),
    path('<int:job_id>/apply/', ApplyJobView.as_view(), name='job-apply'),

    # Employer Management
    path('applications/received/', EmployerApplicationsView.as_view(), name='employer-applications'),
]