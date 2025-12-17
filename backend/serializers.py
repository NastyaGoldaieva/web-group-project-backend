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
    whatsapp_username = serializers.CharField(write_only=True, required=True)
    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name', 'last_name', 'role', 'whatsapp_username')
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ця пошта вже використовується.")
        return value
    def create(self, validated_data):
        whatsapp = validated_data.pop('whatsapp_username', '')
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
            MentorProfile.objects.create(user=user, whatsapp_username=whatsapp)
        else:
            StudentProfile.objects.create(user=user, whatsapp_username=whatsapp)
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
        fields = ('id', 'username', 'bio', 'interests', 'contact', 'location', 'availability', 'whatsapp_username')
        read_only_fields = ('id', 'username')

class MentorProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    class Meta:
        model = MentorProfile
        fields = ('id', 'username', 'user_id', 'title', 'bio', 'skills', 'location', 'contact', 'availability', 'whatsapp_username', 'created_at')

MentorSerializer = MentorProfileSerializer

class MentorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorProfile
        fields = ('title', 'bio', 'skills', 'location', 'contact', 'availability', 'whatsapp_username')

class RequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.username', read_only=True)
    mentor_name = serializers.CharField(source='mentor.username', read_only=True)
    mentor = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    class Meta:
        model = Request
        fields = ('id', 'student', 'mentor', 'student_name', 'mentor_name', 'message', 'status', 'created_at')
        read_only_fields = ('id', 'created_at', 'student', 'status')
    def validate_mentor(self, value):
        request = self.context.get('request')
        if request and value == request.user:
            raise serializers.ValidationError("Не можна відправляти запит самому собі.")
        if getattr(value, 'role', None) != User.ROLE_MENTOR:
            raise serializers.ValidationError("Цільовий користувач не є ментором.")
        return value

class ProposalSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    mentor_username = serializers.CharField(source='mentor.username', read_only=True)
    meeting_id = serializers.SerializerMethodField()
    meet_link = serializers.SerializerMethodField()
    whatsapp_shared = serializers.SerializerMethodField()
    mentor_whatsapp = serializers.SerializerMethodField()
    student_whatsapp = serializers.SerializerMethodField()
    meeting_start = serializers.SerializerMethodField()
    meeting_end = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = ('id', 'request', 'mentor', 'mentor_username', 'student', 'student_username', 'slots', 'status', 'chosen_slot', 'created_at',
                  'meeting_id', 'meet_link', 'whatsapp_shared', 'mentor_whatsapp', 'student_whatsapp', 'meeting_start', 'meeting_end')
        read_only_fields = ('id', 'created_at', 'mentor_username', 'student_username', 'meeting_id', 'meet_link', 'whatsapp_shared', 'mentor_whatsapp', 'student_whatsapp', 'meeting_start', 'meeting_end')

    def _get_latest_meeting(self, obj):
        try:
            return Meeting.objects.filter(student=obj.student, mentor=obj.mentor).order_by('-created_at').first()
        except Exception:
            return None

    def get_meeting_id(self, obj):
        m = self._get_latest_meeting(obj)
        return m.id if m else None

    def get_meet_link(self, obj):
        m = self._get_latest_meeting(obj)
        return m.meet_link if m else ""

    def get_whatsapp_shared(self, obj):
        m = self._get_latest_meeting(obj)
        return bool(m.whatsapp_shared) if m else False

    def get_mentor_whatsapp(self, obj):
        m = self._get_latest_meeting(obj)
        if m and m.whatsapp_shared:
            prof = getattr(m.mentor, "mentor_profile", None)
            if prof and prof.whatsapp_username:
                return f"https://wa.me/{prof.whatsapp_username}"
        return ""

    def get_student_whatsapp(self, obj):
        m = self._get_latest_meeting(obj)
        if m and m.whatsapp_shared:
            prof = getattr(m.student, "student_profile", None)
            if prof and prof.whatsapp_username:
                return f"https://wa.me/{prof.whatsapp_username}"
        return ""

    def get_meeting_start(self, obj):
        m = self._get_latest_meeting(obj)
        if m and m.start:
            return m.start.isoformat()
        return None

    def get_meeting_end(self, obj):
        m = self._get_latest_meeting(obj)
        if m and m.end:
            return m.end.isoformat()
        return None

class MeetingSerializer(serializers.ModelSerializer):
    mentor_username = serializers.CharField(source='mentor.username', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    mentor_whatsapp = serializers.SerializerMethodField()
    student_whatsapp = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = ('id', 'mentor', 'mentor_username', 'student', 'student_username', 'start', 'end', 'status', 'meet_link', 'created_at',
                  'student_attended', 'student_liked', 'student_continue',
                  'mentor_attended', 'mentor_liked', 'mentor_continue',
                  'whatsapp_shared', 'mentor_whatsapp', 'student_whatsapp')

    def get_mentor_whatsapp(self, obj):
        if obj.whatsapp_shared:
            prof = getattr(obj.mentor, "mentor_profile", None)
            if prof and prof.whatsapp_username:
                return f"https://wa.me/{prof.whatsapp_username}"
        return ""

    def get_student_whatsapp(self, obj):
        if obj.whatsapp_shared:
            prof = getattr(obj.student, "student_profile", None)
            if prof and prof.whatsapp_username:
                return f"https://wa.me/{prof.whatsapp_username}"
        return ""