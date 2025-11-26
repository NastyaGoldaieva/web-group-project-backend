from rest_framework import generics, viewsets, permissions, exceptions
from .models import StudentProfile, Request, MentorProfile
from .serializers import StudentProfileSerializer, RequestSerializer, RegisterSerializer, UserSerializer, MentorSerializer, MentorUpdateSerializer
from .permissions import IsOwnerOrReadOnly
from .pagination import StandardResultsSetPagination

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        return self.request.user

class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

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