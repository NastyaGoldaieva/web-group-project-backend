from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import StudentProfile, Request, MentorProfile

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "bio")

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ("username", "email", "password", "role", "first_name", "last_name")
    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

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

class MentorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = MentorProfile
        fields = ("id", "user", "title", "bio", "skills", "location", "contact", "availability", "created_at")

class MentorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorProfile
        fields = ("title", "bio", "skills", "location", "contact", "availability")