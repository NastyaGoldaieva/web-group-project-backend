from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .models import StudentProfile, MentorProfile, Request, Proposal, Meeting
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

User = get_user_model()



class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name', 'role')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ця пошта вже використовується.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', 'student'),
            is_active=False
        )

        if user.role == User.ROLE_MENTOR:
            MentorProfile.objects.create(user=user)
        else:
            StudentProfile.objects.create(user=user)

        return user


class ActivateAccountSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Невірне посилання активації")

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError("Токен недійсний або застарів")

        self.user = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Невірний ідентифікатор")

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError("Токен недійсний або застарів")

        self.user = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role')


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            RefreshToken(self.token).blacklist()
        except Exception:
            pass



class StudentProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StudentProfile
        fields = ('id', 'username', 'bio', 'interests', 'contact', 'location', 'availability')
        read_only_fields = ('id', 'username')


class MentorProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = MentorProfile
        fields = (
        'id', 'username', 'user_id', 'title', 'bio', 'skills', 'location', 'contact', 'availability', 'created_at')


MentorSerializer = MentorProfileSerializer


class MentorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorProfile
        fields = ('title', 'bio', 'skills', 'location', 'contact', 'availability')



class RequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)
    mentor_name = serializers.CharField(source='mentor.username', read_only=True)

    class Meta:
        model = Request
        fields = ('id', 'student', 'mentor', 'student_name', 'mentor_name', 'message', 'status', 'created_at')
        read_only_fields = ('id', 'created_at', 'student', 'status')


class ProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        fields = ('id', 'request', 'mentor', 'student', 'slots', 'status', 'chosen_slot', 'created_at')


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ('id', 'mentor', 'student', 'start', 'end', 'status', 'meet_link', 'created_at')