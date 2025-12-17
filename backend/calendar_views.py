from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Meeting
from . import utils
class MeetingAddToCalendarView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        meeting = get_object_or_404(Meeting, pk=pk)
        if request.user != meeting.student and request.user != meeting.mentor:
            return Response({'detail': 'Forbidden'}, status=403)
        start = meeting.start
        end = meeting.end
        summary = f"Meeting #{meeting.id}: {meeting.student.username} ⇄ {meeting.mentor.username}"
        description = f"Meet link: {meeting.meet_link or ''}"
        attendees = []
        if meeting.student.email:
            attendees.append(meeting.student.email)
        if meeting.mentor.email and meeting.mentor.email not in attendees:
            attendees.append(meeting.mentor.email)
        organizer_email = request.user.email or None
        try:
            link = utils.create_google_meet_event(start, end, summary, description, attendees, organizer_email=organizer_email)
            if link:
                if not meeting.meet_link:
                    meeting.meet_link = link
                    meeting.save(update_fields=['meet_link'])
                return Response({'status': 'ok', 'link': link})
            return Response({'status': 'error', 'detail': 'No link created'}, status=500)
        except Exception as e:
            return Response({'status': 'error', 'detail': str(e)}, status=500)