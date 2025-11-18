from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_MENTOR = "mentor"
    ROLE_STUDENT = "student"
    ROLE_CHOICES = [
        (ROLE_MENTOR, "Mentor"),
        (ROLE_STUDENT, "Student"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_STUDENT)
    bio = models.TextField(blank=True)

    def is_mentor(self):
        return self.role == self.ROLE_MENTOR

    def __str__(self):
        return f"{self.username} ({self.role})"
