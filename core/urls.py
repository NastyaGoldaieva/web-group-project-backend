from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from backend.views import StudentProfileViewSet, RequestViewSet

# 👇 1. Імпортуємо view для токенів
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

router = DefaultRouter()
router.register(r'students', StudentProfileViewSet)
router.register(r'requests', RequestViewSet, basename='requests')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),

    # 👇 2. Ось ці "двері", яких не вистачало!
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]