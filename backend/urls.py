from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    RegisterView,
    MeView,
    StudentProfileViewSet,
    RequestViewSet,
    MentorViewSet,
    ProposalViewSet,
    MeetingViewSet,
    LogoutView,
    ActivateAccountView,
    PasswordResetRequestView,
    PasswordResetConfirmView, GoogleLoginView, GoogleRegisterView
)
from .calendar_views import MeetingAddToCalendarView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
router = DefaultRouter()
router.register(r"students", StudentProfileViewSet, basename="student")
router.register(r"mentors", MentorViewSet, basename="mentor")
router.register(r"requests", RequestViewSet, basename="request")
router.register(r"proposals", ProposalViewSet, basename="proposal")
router.register(r"meetings", MeetingViewSet, basename="meeting")
urlpatterns = [
    path("auth/google/register/", GoogleRegisterView.as_view(), name="google_register"),
    path("auth/google/", GoogleLoginView.as_view(), name="google_login"),
    path("meetings/<int:pk>/add_to_calendar/", MeetingAddToCalendarView.as_view(), name="meeting-add-to-calendar"),
    path("", include(router.urls)),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/activate/", ActivateAccountView.as_view(), name="activate"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
]