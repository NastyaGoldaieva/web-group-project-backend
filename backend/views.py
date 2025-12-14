from rest_framework import generics, viewsets, permissions, exceptions, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import StudentProfile, Request, MentorProfile, Proposal, Meeting
from .serializers import (
    StudentProfileSerializer,
    RequestSerializer,
    RegisterSerializer,
    UserSerializer,
    MentorSerializer,
    MentorUpdateSerializer,
    LogoutSerializer,
    ProposalSerializer,
    MeetingSerializer,
    ActivateAccountSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)
from .permissions import IsOwnerOrReadOnly
from .pagination import StandardResultsSetPagination
from .utils import compute_common_slots, generate_meet_link, parse_iso_to_utc
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        activation_link = f"http://localhost:5173/activate/{uid}/{token}"
        try:
            send_mail(
                subject="Підтвердження реєстрації в MentorMatch",
                message=f"Привіт, {user.username}! \nБудь ласка, перейдіть за посиланням, щоб активувати акаунт:\n{activation_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass

class ActivateAccountView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ActivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        user.is_active = True
        user.save()
        return Response({"detail": "Акаунт успішно активовано!"}, status=status.HTTP_200_OK)

class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Якщо пошта існує, ми надіслали інструкції."}, status=status.HTTP_200_OK)
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_link = f"http://localhost:5173/reset-password/{uid}/{token}"
        try:
            send_mail(
                subject="Скидання пароля MentorMatch",
                message=f"Посилання: {reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True
            )
        except Exception:
            pass
        return Response({"detail": "Якщо пошта існує, ми надіслали інструкції."}, status=status.HTTP_200_OK)

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"detail": "Пароль успішно змінено!"}, status=status.HTTP_200_OK)

class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.select_related("user").all()
    serializer_class = StudentProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get', 'post', 'patch'], permission_classes=[IsAuthenticated])
    def me(self, request):
        user = request.user
        profile = getattr(user, 'student_profile', None)
        if request.method == 'GET':
            if not profile:
                return Response(status=status.HTTP_404_NOT_FOUND)
            serializer = StudentProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        if request.method == 'POST':
            if profile:
                return Response({"detail": "Profile already exists."}, status=status.HTTP_400_BAD_REQUEST)
            serializer = StudentProfileSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        if request.method == 'PATCH':
            if not profile:
                return Response({"detail": "Profile does not exist."}, status=status.HTTP_404_NOT_FOUND)
            serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

class RequestViewSet(viewsets.ModelViewSet):
    serializer_class = RequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Request.objects.filter(student=user) | Request.objects.filter(mentor=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        if self.request.user.role != User.ROLE_STUDENT:
            raise exceptions.ValidationError("Тільки студенти можуть відправляти запити.")
        mentor = serializer.validated_data.get('mentor')
        if mentor is None:
            raise exceptions.ValidationError("mentor is required.")
        if mentor == self.request.user:
            raise exceptions.ValidationError("Не можна відправляти запит самому собі.")
        if getattr(mentor, 'role', None) != User.ROLE_MENTOR:
            raise exceptions.ValidationError("Цільовий користувач не є ментором.")
        existing = Request.objects.filter(student=self.request.user, mentor=mentor).first()
        if existing:
            if existing.status == 'rejected':
                existing.message = serializer.validated_data.get('message', existing.message)
                existing.status = 'pending'
                existing.save()
                instance = existing
            else:
                raise exceptions.ValidationError("Ви вже відправили запит цьому ментору.")
        else:
            instance = serializer.save(student=self.request.user)
        try:
            send_mail(
                subject=f"Новий запит від {instance.student.username}",
                message=f"Студент {instance.student.username} надіслав вам запит:\n\n\"{instance.message}\"\n\nЗайдіть в кабінет.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentor.email],
                fail_silently=True
            )
        except Exception:
            pass
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{mentor.id}",
            {
                "type": "notify",
                "event": "new_request",
                "data": {
                    "request_id": instance.id,
                    "student": instance.student.username,
                    "message": instance.message,
                    "status": instance.status
                }
            }
        )

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def accept(self, request, pk=None):
        req = self.get_object()
        if request.user != req.mentor:
            return Response({"detail": "Only mentor can accept."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != 'pending':
            return Response({"detail": "Request already processed."}, status=status.HTTP_400_BAD_REQUEST)
        req.status = 'accepted'
        req.save()
        student_profile = getattr(req.student, 'student_profile', None)
        mentor_profile = getattr(req.mentor, 'mentor_profile', None)
        student_avail = student_profile.availability if student_profile else []
        mentor_avail = mentor_profile.availability if mentor_profile else []
        duration = int(request.data.get('duration', 60))
        step = int(request.data.get('step', 30))
        limit = int(request.data.get('limit', 20))
        slots = compute_common_slots(student_avail, mentor_avail, duration, step, limit)
        proposal = Proposal.objects.create(
            request=req,
            mentor=req.mentor,
            student=req.student,
            slots=slots,
            status='pending'
        )
        try:
            send_mail(
                subject="Ваш запит прийнято!",
                message=f"Ментор {req.mentor.username} прийняв ваш запит. Оберіть час для зустрічі.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[req.student.email],
                fail_silently=True
            )
        except Exception:
            pass
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{req.student.id}",
            {
                "type": "notify",
                "event": "request_accepted",
                "data": {
                    "request_id": req.id,
                    "proposal_id": proposal.id,
                    "slots": proposal.slots
                }
            }
        )
        serializer = ProposalSerializer(proposal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def reject(self, request, pk=None):
        req = self.get_object()
        if request.user != req.mentor:
            return Response({"detail": "Тільки ментор може відхилити запит."}, status=status.HTTP_403_FORBIDDEN)
        req.status = 'rejected'
        req.save()
        try:
            send_mail(
                subject="Оновлення статусу запиту",
                message=f"На жаль, ментор {req.mentor.username} відхилив ваш запит.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[req.student.email],
                fail_silently=True
            )
        except Exception:
            pass
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{req.student.id}",
            {
                "type": "notify",
                "event": "request_rejected",
                "data": {
                    "request_id": req.id,
                    "status": req.status
                }
            }
        )
        return Response(RequestSerializer(req).data, status=status.HTTP_200_OK)

class MentorViewSet(viewsets.ModelViewSet):
    queryset = MentorProfile.objects.select_related("user").all()
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ["partial_update", "update", "create", "destroy", "me"]:
            return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.action in ["partial_update", "update", "create", "me"]:
            return MentorUpdateSerializer
        return MentorSerializer

    def get_queryset(self):
        qs = self.queryset
        skill = self.request.query_params.get("skill")
        location = self.request.query_params.get("location")
        if skill:
            qs = qs.filter(skills__icontains=skill)
        if location:
            qs = qs.filter(location__icontains=location)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])
    def me(self, request):
        user = request.user
        try:
            profile = user.mentor_profile
        except MentorProfile.DoesNotExist:
            return Response({"detail": "Mentor profile not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == 'GET':
            serializer = MentorSerializer(profile)
            return Response(serializer.data)
        if request.method == 'PATCH':
            serializer = MentorUpdateSerializer(profile, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

class ProposalViewSet(viewsets.ModelViewSet):
    queryset = Proposal.objects.select_related("mentor", "student").all()
    serializer_class = ProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Proposal.objects.filter(mentor=user) | Proposal.objects.filter(student=user)

    @action(detail=True, methods=['post'])
    def select(self, request, pk=None):
        proposal = self.get_object()
        if request.user != proposal.student:
            return Response({"detail": "Only student can choose a slot."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != 'pending':
            return Response({"detail": "Cannot select on non-pending proposal."}, status=status.HTTP_400_BAD_REQUEST)
        chosen = request.data.get('chosen_slot')
        if not chosen or 'start' not in chosen or 'end' not in chosen:
            return Response({"detail": "Provide chosen_slot with start and end ISO strings."}, status=status.HTTP_400_BAD_REQUEST)
        if chosen not in proposal.slots:
            return Response({"detail": "Chosen slot not in proposed slots."}, status=status.HTTP_400_BAD_REQUEST)
        proposal.chosen_slot = chosen
        proposal.status = 'student_chosen'
        proposal.save()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{proposal.mentor.id}",
            {
                "type": "notify",
                "event": "proposal_student_chosen",
                "data": {
                    "proposal_id": proposal.id,
                    "chosen_slot": proposal.chosen_slot,
                    "status": proposal.status
                }
            }
        )
        return Response(ProposalSerializer(proposal).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        proposal = self.get_object()
        if request.user != proposal.mentor:
            return Response({"detail": "Only mentor can confirm."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != 'student_chosen':
            return Response({"detail": "No slot chosen by student yet."}, status=status.HTTP_400_BAD_REQUEST)
        chosen = proposal.chosen_slot
        try:
            start_dt = parse_iso_to_utc(chosen.get('start'))
            end_dt = parse_iso_to_utc(chosen.get('end'))
            if not start_dt or not end_dt:
                raise ValueError("Invalid datetimes")
        except Exception:
            return Response({"detail": "Invalid chosen slot format."}, status=status.HTTP_400_BAD_REQUEST)
        meet_link = generate_meet_link()
        meeting = Meeting.objects.create(
            mentor=proposal.mentor,
            student=proposal.student,
            start=start_dt,
            end=end_dt,
            status='scheduled',
            meet_link=meet_link
        )
        proposal.status = 'confirmed'
        proposal.save()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{proposal.student.id}",
            {
                "type": "notify",
                "event": "proposal_confirmed",
                "data": {
                    "proposal_id": proposal.id,
                    "meeting_id": meeting.id
                }
            }
        )
        return Response({
            'proposal': ProposalSerializer(proposal).data,
            'meeting': MeetingSerializer(meeting).data
        }, status=status.HTTP_201_CREATED)

class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.select_related("mentor", "student").all()
    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Meeting.objects.filter(mentor=user) | Meeting.objects.filter(student=user)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)