from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegisterView, MeView, MentorViewSet, StudentProfileViewSet, RequestViewSet, LogoutView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register(r"mentors", MentorViewSet, basename="mentor")
router.register(r"students", StudentProfileViewSet, basename="student")
router.register(r"requests", RequestViewSet, basename="request")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("", include(router.urls)),
]