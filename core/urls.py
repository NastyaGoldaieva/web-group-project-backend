from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from backend.views import StudentProfileViewSet, RequestViewSet

# router = DefaultRouter()
# router.register(r'students', StudentProfileViewSet)
# router.register(r'requests', RequestViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/', include('backend.urls')),
]
