from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import StudentProfile, Request, User, MentorProfile

admin.site.register(StudentProfile)
admin.site.register(Request)
admin.site.register(MentorProfile)

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Additional", {"fields": ("role", "bio")}),
    )