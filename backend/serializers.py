from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import StudentProfile, MentorProfile, Request, Proposal, Meeting

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role')

class StudentProfileSerializer(serializers.ModelSerializer):
    # If you want to expose username on profile responses:
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StudentProfile
        # removed 'study_year'
        fields = ('id', 'username', 'bio', 'interests', 'contact', 'location', 'availability')
        read_only_fields = ('id', 'username')

# Other serializers (keep your existing implementations)
class MentorProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    class Meta:
        model = MentorProfile
        fields = ('id', 'username', 'title', 'bio', 'skills', 'location', 'contact', 'availability', 'created_at')

class RequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)
    mentor_name = serializers.CharField(source='mentor.username', read_only=True)
    class Meta:
        model = Request
        fields = ('id', 'student', 'mentor', 'student_name', 'mentor_name', 'message', 'status', 'created_at')
        read_only_fields = ('id', 'created_at')

class ProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        fields = ('id', 'request', 'mentor', 'student', 'slots', 'status', 'chosen_slot', 'created_at')

class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ('id', 'mentor', 'student', 'start', 'end', 'status', 'meet_link', 'created_at')