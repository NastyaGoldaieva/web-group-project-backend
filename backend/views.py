from rest_framework import viewsets, permissions, exceptions
from .models import StudentProfile, Request
from .serializers import StudentProfileSerializer, RequestSerializer
from .permissions import IsOwnerOrReadOnly


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