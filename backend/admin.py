from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import StudentProfile, Request, User, MentorProfile, Proposal, Meeting

admin.site.register(StudentProfile)
admin.site.register(Request)
admin.site.register(MentorProfile)
admin.site.register(Proposal)
admin.site.register(Meeting)

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Additional", {"fields": ("role", "bio")}),
    )