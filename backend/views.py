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
)
from .permissions import IsOwnerOrReadOnly
from .pagination import StandardResultsSetPagination
from .utils import compute_common_slots, generate_meet_link, parse_iso_to_utc
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


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
        """
        GET  /api/students/me/  -> return current user's profile or 404
        POST /api/students/me/  -> create profile for current user (if none)
        PATCH /api/students/me/ -> update profile for current user (if exists)
        """
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

        # PATCH
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

    def perform_create(self, serializer):
        mentor = serializer.validated_data['mentor']
        if Request.objects.filter(student=self.request.user, mentor=mentor).exists():
            raise exceptions.ValidationError("Ви вже відправили запит цьому ментору.")
        serializer.save(student=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def accept(self, request, pk=None):
        """Mentor accepts request -> create Proposal with computed slots."""
        req = self.get_object()
        if request.user != req.mentor:
            return Response({"detail": "Only mentor can accept."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != 'pending':
            return Response({"detail": "Request already processed."}, status=status.HTTP_400_BAD_REQUEST)
        # mark request accepted
        req.status = 'accepted'
        req.save()
        # gather availabilities
        student_profile = getattr(req.student, 'student_profile', None)
        mentor_profile = getattr(req.mentor, 'mentor_profile', None)
        student_avail = student_profile.availability if student_profile else []
        mentor_avail = mentor_profile.availability if mentor_profile else []
        # compute slots
        duration = int(request.data.get('duration', 60))  # minutes
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
        serializer = ProposalSerializer(proposal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MentorViewSet(viewsets.ModelViewSet):
    queryset = MentorProfile.objects.select_related("user").all()
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action in ["partial_update", "update", "create", "destroy"]:
            return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.action in ["partial_update", "update", "create"]:
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


class ProposalViewSet(viewsets.ModelViewSet):
    queryset = Proposal.objects.select_related("mentor", "student").all()
    serializer_class = ProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Proposal.objects.filter(mentor=user) | Proposal.objects.filter(student=user)

    @action(detail=True, methods=['post'])
    def select(self, request, pk=None):
        """Student selects a slot from proposal.slots"""
        proposal = self.get_object()
        if request.user != proposal.student:
            return Response({"detail": "Only student can choose a slot."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != 'pending':
            return Response({"detail": "Cannot select on non-pending proposal."}, status=status.HTTP_400_BAD_REQUEST)
        chosen = request.data.get('chosen_slot')
        if not chosen or 'start' not in chosen or 'end' not in chosen:
            return Response({"detail": "Provide chosen_slot with start and end ISO strings."}, status=status.HTTP_400_BAD_REQUEST)
        # validate the chosen slot exists in slots
        if chosen not in proposal.slots:
            return Response({"detail": "Chosen slot not in proposed slots."}, status=status.HTTP_400_BAD_REQUEST)
        proposal.chosen_slot = chosen
        proposal.status = 'student_chosen'
        proposal.save()
        return Response(ProposalSerializer(proposal).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Mentor confirms student's chosen slot -> create Meeting"""
        proposal = self.get_object()
        if request.user != proposal.mentor:
            return Response({"detail": "Only mentor can confirm."}, status=status.HTTP_403_FORBIDDEN)
        if proposal.status != 'student_chosen':
            return Response({"detail": "No slot chosen by student yet."}, status=status.HTTP_400_BAD_REQUEST)
        chosen = proposal.chosen_slot
        # parse chosen ISO strings into timezone-aware datetimes
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