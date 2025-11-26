from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegisterView, MeView, MentorViewSet, StudentProfileViewSet, RequestViewSet

router = DefaultRouter()
router.register(r"mentors", MentorViewSet, basename="mentor")
router.register(r"students", StudentProfileViewSet, basename="student")
router.register(r"requests", RequestViewSet, basename="request")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]