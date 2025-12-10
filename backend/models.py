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


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    bio = models.TextField(blank=True, verbose_name="Про себе")
    interests = models.CharField(max_length=255, blank=True, verbose_name="Інтереси/Навички")
    contact = models.CharField(max_length=100, blank=True, verbose_name="Контакт (Telegram/Email)")
    location = models.CharField(max_length=100, blank=True, verbose_name="Місто/Країна")
    availability = models.JSONField(blank=True, null=True, default=list, verbose_name="Availability (UTC intervals)")

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

class MentorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='mentor_profile')
    title = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    skills = models.CharField(max_length=500, blank=True)
    location = models.CharField(max_length=200, blank=True)
    contact = models.CharField(max_length=200, blank=True)
    availability = models.JSONField(blank=True, null=True, default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Mentor: {self.user.username} - {self.title or 'Mentor'}"


class Proposal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('student_chosen', 'Student chosen'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='proposals', null=True, blank=True)
    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='proposals_as_mentor')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='proposals_as_student')
    slots = models.JSONField(default=list)  # list of {"start": iso, "end": iso}
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    chosen_slot = models.JSONField(null=True, blank=True)  # {"start": iso, "end": iso}
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proposal {self.id} {self.student.username} <-> {self.mentor.username} ({self.status})"


class Meeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meetings_as_mentor')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meetings_as_student')
    start = models.DateTimeField()
    end = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    meet_link = models.CharField(max_length=1024, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Meeting {self.id} {self.student.username} <-> {self.mentor.username} at {self.start.isoformat()}"