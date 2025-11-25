from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import User

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


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    bio = models.TextField(blank=True, verbose_name="Про себе")
    interests = models.CharField(max_length=255, blank=True, verbose_name="Інтереси/Навички")
    study_year = models.PositiveIntegerField(default=1, verbose_name="Курс навчання")
    contact = models.CharField(max_length=100, blank=True, verbose_name="Контакт (Telegram/Email)")
    location = models.CharField(max_length=100, blank=True, verbose_name="Місто/Країна")

    def __str__(self):
        return f"Student: {self.user.username}"

class Request(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Очікує'),
        ('accepted', 'Прийнято'),
        ('rejected', 'Відхилено'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    message = models.TextField(verbose_name="Повідомлення ментору")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'mentor')
        ordering = ['-created_at']

    def __str__(self):
        return f"From {self.student.username} to {self.mentor.username} ({self.status})"
