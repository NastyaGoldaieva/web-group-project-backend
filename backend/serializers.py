from rest_framework import serializers
from django.contrib.auth.models import User
from .models import StudentProfile, Request

class StudentProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = StudentProfile
        fields = ['id', 'username', 'email', 'bio', 'interests', 'study_year', 'contact', 'location']
        read_only_fields = ['username', 'email']

class RequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)
    mentor_name = serializers.CharField(source='mentor.username', read_only=True)

    class Meta:
        model = Request
        fields = ['id', 'student', 'student_name', 'mentor', 'mentor_name', 'message', 'status', 'created_at']
        read_only_fields = ['student', 'status', 'created_at']