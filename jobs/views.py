from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import JobPosting, JobApplication, SeekerProfile
from .serializers import JobPostingSerializer, JobApplicationSerializer, SeekerProfileSerializer

# --- PUBLIC / SEEKER JOB SEARCH ---

class JobListView(generics.ListCreateAPIView):
    """
    GET: Public list of open jobs.
    POST: Employer posts a new job.
    """
    queryset = JobPosting.objects.filter(status='open')
    serializer_class = JobPostingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'description', 'requirements']

    def perform_create(self, serializer):
        # Check if user is an Employer
        if 'employer' not in self.request.user.roles:
            raise PermissionDenied("Only Employers can post jobs.")
        serializer.save(employer=self.request.user)

class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: View job details.
    PUT/DELETE: Only the Employer who posted it.
    """
    queryset = JobPosting.objects.all()
    serializer_class = JobPostingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_update(self, serializer):
        if self.get_object().employer != self.request.user:
            raise PermissionDenied("You cannot edit this job.")
        serializer.save()

# --- SEEKER ACTIONS ---

class SeekerProfileView(generics.RetrieveUpdateAPIView):
    """
    Manage your CV / Profile.
    """
    serializer_class = SeekerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Get or create profile for current user
        obj, created = SeekerProfile.objects.get_or_create(user=self.request.user)
        return obj

class ApplyJobView(generics.CreateAPIView):
    """
    Apply for a specific job ID.
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        job_id = self.kwargs.get('job_id')
        
        # 1. Check Role
        if 'job_seeker' not in user.roles and 'worker' not in user.roles:
             # Auto-add role or raise error? Let's be strict for now.
             raise PermissionDenied("You must have a Job Seeker profile to apply.")

        # 2. Check if already applied
        if JobApplication.objects.filter(job_id=job_id, seeker=user).exists():
            raise PermissionDenied("You have already applied for this job.")

        job = JobPosting.objects.get(pk=job_id)
        serializer.save(seeker=user, job=job)

# --- EMPLOYER DASHBOARD ---

class EmployerApplicationsView(generics.ListAPIView):
    """
    View all applications for MY jobs.
    """
    serializer_class = JobApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return applications where the job's employer is ME
        return JobApplication.objects.filter(job__employer=self.request.user)