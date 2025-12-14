from datetime import datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import generics, viewsets, permissions, exceptions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

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
    PasswordResetConfirmSerializer,
)
from .permissions import IsOwnerOrReadOnly
from .pagination import StandardResultsSetPagination
from .utils import compute_common_slots, generate_meet_link, parse_iso_to_utc, create_google_meet_event
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken
import os

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        try:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            activation_link = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/activate/{uid}/{token}"
            send_mail(
                subject="Confirm your MentorMatch registration",
                message=f"Hello {user.username}, confirm your account: {activation_link}",
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
        return Response({"detail": "Account activated"}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/reset-password/{uid}/{token}"
            send_mail(
                subject="Password reset for MentorMatch",
                message=f"If you requested a password reset, use this link: {reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
        except User.DoesNotExist:
            pass
        return Response({"detail": "If the email exists, instructions were sent."}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password changed"}, status=status.HTTP_200_OK)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.select_related("user").all()
    serializer_class = StudentProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get", "post", "patch"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        user = request.user
        profile = getattr(user, "student_profile", None)
        if request.method == "GET":
            if not profile:
                return Response(status=status.HTTP_404_NOT_FOUND)
            serializer = StudentProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        if request.method == "POST":
            if profile:
                return Response({"detail": "Profile already exists."}, status=status.HTTP_400_BAD_REQUEST)
            serializer = StudentProfileSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        if request.method == "PATCH":
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

    def perform_create(self, serializer):
        if self.request.user.role != User.ROLE_STUDENT:
            raise exceptions.ValidationError("Only students can send requests.")
        mentor = serializer.validated_data.get("mentor")
        if mentor is None:
            raise exceptions.ValidationError("mentor is required.")
        if mentor == self.request.user:
            raise exceptions.ValidationError("You cannot send a request to yourself.")
        if getattr(mentor, "role", None) != User.ROLE_MENTOR:
            raise exceptions.ValidationError("Target user is not a mentor.")
        if Request.objects.filter(student=self.request.user, mentor=mentor).exists():
            raise exceptions.ValidationError("You have already sent a request to this mentor.")

        instance = serializer.save(student=self.request.user)

        try:
            send_mail(
                subject=f"New request from {instance.student.username}",
                message=f"Student {instance.student.username} sent you a request:\n\n\"{instance.message}\"",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[mentor.email],
                fail_silently=True,
            )
        except Exception:
            pass

        try:
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
                        "status": instance.status,
                    },
                },
            )
        except Exception:
            pass

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def accept(self, request, pk=None):
        req = self.get_object()
        if request.user != req.mentor:
            return Response({"detail": "Only mentor can accept."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != "pending":
            return Response({"detail": "Request already processed."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = "accepted"
        req.save()

        proposal = Proposal.objects.create(
            request=req, mentor=req.mentor, student=req.student, slots=[], status="awaiting_mentor"
        )

        try:
            send_mail(
                subject="Please provide your available days/times",
                message=(
                    f"Please indicate your available days/times for the meeting: "
                    f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/mentor/proposals/{proposal.id}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[req.mentor.email],
                fail_silently=True,
            )
        except Exception:
            pass

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{req.mentor.id}",
                {
                    "type": "notify",
                    "event": "request_accepted_need_slots",
                    "data": {"request_id": req.id, "proposal_id": proposal.id},
                },
            )
        except Exception:
            pass

        return Response(ProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def reject(self, request, pk=None):
        req = self.get_object()
        if request.user != req.mentor:
            return Response({"detail": "Only mentor can reject."}, status=status.HTTP_403_FORBIDDEN)
        req.status = "rejected"
        req.save()
        try:
            send_mail(
                subject="Request update",
                message=f"Unfortunately mentor {req.mentor.username} rejected your request.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[req.student.email],
                fail_silently=True,
            )
        except Exception:
            pass
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{req.student.id}",
                {
                    "type": "notify",
                    "event": "request_rejected",
                    "data": {"request_id": req.id, "status": req.status},
                },
            )
        except Exception:
            pass
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

    @action(detail=False, methods=["get", "patch"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        user = request.user
        try:
            profile = user.mentor_profile
        except MentorProfile.DoesNotExist:
            return Response({"detail": "Mentor profile not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == "GET":
            serializer = MentorSerializer(profile)
            return Response(serializer.data)
        if request.method == "PATCH":
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

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def propose_slots(self, request, pk=None):
        proposal = self.get_object()
        if request.user != proposal.mentor:
            return Response({"detail": "Only mentor can propose slots."}, status=status.HTTP_403_FORBIDDEN)

        slots = request.data.get("slots")
        if not isinstance(slots, list) or not slots:
            return Response({"detail": "Provide a non-empty list of slots."}, status=status.HTTP_400_BAD_REQUEST)

        valid = []
        for it in slots:
            s = it.get("start")
            e = it.get("end")
            try:
                sd = parse_iso_to_utc(s)
                ed = parse_iso_to_utc(e)
                if not sd or not ed or sd >= ed:
                    raise ValueError()
            except Exception:
                return Response({"detail": "Invalid slot format. Use ISO datetimes."},
                                status=status.HTTP_400_BAD_REQUEST)
            valid.append({"start": s, "end": e})

        proposal.slots = valid
        proposal.status = "pending"
        proposal.save()

        try:
            send_mail(
                subject="Time proposal from mentor",
                message=(
                        f"Mentor {proposal.mentor.username} proposed slots:\n\n"
                        + "\n".join([f"{x['start']} - {x['end']}" for x in valid])
                        + f"\n\nChoose a slot in your dashboard: {getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')}/proposals/{proposal.id}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[proposal.student.email],
                fail_silently=True,
            )
        except Exception:
            pass

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{proposal.student.id}",
                {
                    "type": "notify",
                    "event": "mentor_proposed_slots",
                    "data": {"proposal_id": proposal.id, "slots": proposal.slots},
                },
            )
        except Exception:
            pass

        return Response(ProposalSerializer(proposal).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def select(self, request, pk=None):
        proposal = self.get_object()
        if request.user != proposal.student:
            return Response({"detail": "Only student can choose a slot."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != "pending":
            return Response({"detail": "Cannot select on non-pending proposal."}, status=status.HTTP_400_BAD_REQUEST)

        chosen = request.data.get("chosen_slot")
        if not chosen or "start" not in chosen or "end" not in chosen:
            return Response({"detail": "Provide chosen_slot with start and end ISO strings."},
                            status=status.HTTP_400_BAD_REQUEST)
        if chosen not in proposal.slots:
            return Response({"detail": "Chosen slot not in proposed slots."}, status=status.HTTP_400_BAD_REQUEST)

        proposal.chosen_slot = chosen
        proposal.status = "student_chosen"
        proposal.save()

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{proposal.mentor.id}",
                {
                    "type": "notify",
                    "event": "student_chosen_slot",
                    "data": {"proposal_id": proposal.id, "chosen_slot": proposal.chosen_slot},
                },
            )
        except Exception:
            pass

        return Response(ProposalSerializer(proposal).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        proposal = self.get_object()
        if request.user != proposal.mentor:
            return Response({"detail": "Only mentor can confirm."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != "student_chosen":
            return Response({"detail": "No slot chosen by student yet."}, status=status.HTTP_400_BAD_REQUEST)

        chosen = proposal.chosen_slot
        try:
            start_dt = parse_iso_to_utc(chosen.get("start"))
            end_dt = parse_iso_to_utc(chosen.get("end"))
            if not start_dt or not end_dt:
                raise ValueError("Invalid datetimes")
        except Exception:
            return Response({"detail": "Invalid chosen slot format."}, status=status.HTTP_400_BAD_REQUEST)

        meet_link = create_google_meet_event(
            start_dt,
            end_dt,
            summary=f"Meeting: {proposal.student.username} & {proposal.mentor.username}",
            description=proposal.request.message or "",
            attendees_emails=[proposal.student.email, proposal.mentor.email],
        )

        meeting = Meeting.objects.create(
            mentor=proposal.mentor,
            student=proposal.student,
            start=start_dt,
            end=end_dt,
            status="scheduled",
            meet_link=meet_link,
        )

        proposal.status = "confirmed"
        proposal.save()

        try:
            send_mail(
                subject="Meeting scheduled",
                message=(
                    f"Meeting between {proposal.student.username} and {proposal.mentor.username} scheduled for {chosen.get('start')} — {chosen.get('end')}.\n\n"
                    f"Meet link: {meet_link}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[proposal.student.email, proposal.mentor.email],
                fail_silently=True,
            )
        except Exception:
            pass

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{proposal.student.id}",
                {
                    "type": "notify",
                    "event": "proposal_confirmed",
                    "data": {"proposal_id": proposal.id, "meeting_id": meeting.id, "meet_link": meet_link},
                },
            )
            async_to_sync(channel_layer.group_send)(
                f"user_{proposal.mentor.id}",
                {
                    "type": "notify",
                    "event": "proposal_confirmed",
                    "data": {"proposal_id": proposal.id, "meeting_id": meeting.id, "meet_link": meet_link},
                },
            )
        except Exception:
            pass

        return Response({"proposal": ProposalSerializer(proposal).data, "meeting": MeetingSerializer(meeting).data},
                        status=status.HTTP_201_CREATED)


class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.select_related("mentor", "student").all()
    serializer_class = MeetingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Meeting.objects.filter(mentor=user) | Meeting.objects.filter(student=user)


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'No token provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            id_info = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                os.getenv('GOOGLE_CLIENT_ID')
            )
            email = id_info['email']

            try:
                user = User.objects.get(email=email)

                refresh = RefreshToken.for_user(user)
                return Response({
                    'status': 'login_success',
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': user.role
                    }
                })
            except User.DoesNotExist:
                return Response({
                    'status': 'need_registration',
                    'email': email,
                    'first_name': id_info.get('given_name', ''),
                    'last_name': id_info.get('family_name', ''),
                    'google_token': token
                }, status=status.HTTP_200_OK)

        except ValueError:
            return Response({'error': 'Invalid Google token'}, status=status.HTTP_400_BAD_REQUEST)


class GoogleRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        token = request.data.get('token')
        role = request.data.get('role', 'student')
        username = request.data.get('username')

        if not token or not username:
            return Response({'error': 'Всі поля обов\'язкові'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            id_info = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                os.getenv('GOOGLE_CLIENT_ID')
            )
            email = id_info['email']

            if User.objects.filter(email=email).exists():
                return Response({'error': 'User already exists'}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=id_info.get('given_name', ''),
                last_name=id_info.get('family_name', ''),
                role=role,
                is_active=True
            )

            if role == 'mentor':
                MentorProfile.objects.create(user=user)
            else:
                StudentProfile.objects.create(user=user)

            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(e)
            return Response({'error': 'Registration failed'}, status=status.HTTP_400_BAD_REQUEST)