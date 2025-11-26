from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import MentorProfile

User = get_user_model()

class MentorTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="u1", password="pass12345", role=User.ROLE_MENTOR)
        self.user2 = User.objects.create_user(username="u2", password="pass12345", role=User.ROLE_MENTOR)
        self.mentor1 = MentorProfile.objects.create(user=self.user1, title="Title1", skills="python,django", location="Kyiv")
        self.mentor2 = MentorProfile.objects.create(user=self.user2, title="Title2", skills="js,react", location="Lviv")
    def test_list_mentors(self):
        url = reverse("mentor-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data.get("results", resp.data)), 2)
    def test_retrieve_mentor(self):
        url = reverse("mentor-detail", args=[self.mentor1.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["user"]["username"], "u1")
    def test_update_own_profile(self):
        self.client.login(username="u1", password="pass12345")
        url = reverse("mentor-detail", args=[self.mentor1.id])
        resp = self.client.patch(url, {"bio": "updated"}, format="json")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))
        self.mentor1.refresh_from_db()
        self.assertEqual(self.mentor1.bio, "updated")
    def test_update_other_profile_forbidden(self):
        self.client.login(username="u1", password="pass12345")
        url = reverse("mentor-detail", args=[self.mentor2.id])
        resp = self.client.patch(url, {"bio": "hacked"}, format="json")
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
