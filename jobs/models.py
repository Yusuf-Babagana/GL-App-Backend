from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class SeekerProfile(models.Model):
    """
    Extended profile for Job Seekers containing skills and resume.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='seeker_profile'
    )
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    skills = models.JSONField(default=list) # e.g. ["Python", "React Native"]
    portfolio_url = models.URLField(blank=True, null=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile: {self.user.full_name}"

class Experience(models.Model):
    """
    Work history for a Job Seeker.
    """
    profile = models.ForeignKey(SeekerProfile, on_delete=models.CASCADE, related_name='experiences')
    job_title = models.CharField(max_length=100)
    company_name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.job_title} at {self.company_name}"

class JobPosting(models.Model):
    class JobType(models.TextChoices):
        FULL_TIME = 'full_time', _('Full Time')
        PART_TIME = 'part_time', _('Part Time')
        CONTRACT = 'contract', _('Contract')
        FREELANCE = 'freelance', _('Freelance/Gig')

    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        CLOSED = 'closed', _('Closed')
        FILLED = 'filled', _('Filled')

    employer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='posted_jobs'
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.JSONField(default=list) # List of requirements
    
    # Financials
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='NGN')
    is_negotiable = models.BooleanField(default=False)
    
    # Logistics
    location = models.CharField(max_length=100, default='Remote')
    job_type = models.CharField(
        max_length=20, 
        choices=JobType.choices, 
        default=JobType.FREELANCE
    )
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.OPEN
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"

class JobApplication(models.Model):
    class Status(models.TextChoices):
        APPLIED = 'applied', _('Applied')
        INTERVIEWING = 'interviewing', _('Interviewing')
        HIRED = 'hired', _('Hired')
        REJECTED = 'rejected', _('Rejected')

    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='job_applications'
    )
    cover_letter = models.TextField()
    custom_resume = models.FileField(upload_to='application_resumes/', blank=True, null=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.APPLIED
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('job', 'seeker') # Prevent double applying

    def __str__(self):
        return f"{self.seeker.full_name} -> {self.job.title}"