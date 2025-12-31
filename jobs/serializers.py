from rest_framework import serializers
from .models import SeekerProfile, Experience, JobPosting, JobApplication
from django.contrib.auth import get_user_model

User = get_user_model()

class ExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experience
        fields = ['id', 'job_title', 'company_name', 'start_date', 'end_date', 'is_current', 'description']

class SeekerProfileSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    experiences = ExperienceSerializer(many=True, required=False)

    class Meta:
        model = SeekerProfile
        fields = ['user_name', 'skills', 'resume', 'portfolio_url', 'experiences']

    def update(self, instance, validated_data):
        experiences_data = validated_data.pop('experiences', [])
        # Update main profile
        instance = super().update(instance, validated_data)
        
        # Handle Experience (Simplified: clear and re-add for now)
        if experiences_data:
            instance.experiences.all().delete()
            for exp_data in experiences_data:
                Experience.objects.create(profile=instance, **exp_data)
        return instance

class JobApplicationSerializer(serializers.ModelSerializer):
    seeker_name = serializers.CharField(source='seeker.full_name', read_only=True)
    seeker_email = serializers.CharField(source='seeker.email', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)

    class Meta:
        model = JobApplication
        fields = ['id', 'job', 'job_title', 'seeker', 'seeker_name', 'seeker_email', 'cover_letter', 'custom_resume', 'status', 'created_at']
        read_only_fields = ['job', 'seeker', 'status', 'created_at']

class JobPostingSerializer(serializers.ModelSerializer):
    employer_name = serializers.CharField(source='employer.full_name', read_only=True)
    application_count = serializers.IntegerField(source='applications.count', read_only=True)

    class Meta:
        model = JobPosting
        fields = [
            'id', 'employer', 'employer_name', 'title', 'description', 'requirements',
            'budget', 'currency', 'is_negotiable', 'location', 'job_type', 
            'status', 'application_count', 'created_at'
        ]
        read_only_fields = ['employer', 'status', 'application_count']