# MentorMatch

Short summary
-------
MentorMatch is a web application for connecting mentors and students. The project's goal is to provide a simple platform where learners can find mentors by skills and reviews, schedule sessions, receive assignments, and communicate in real time.

Team
-------
- Goldaieva Anastasiia
- Kovalevska Julia

Brief description of features
------------------------
- User registration and authentication (roles: Mentor, Student).
- Mentor profiles with a list of skills (tags), ratings, and reviews.
- Search for mentors by name or skills.
- Mentorship request system (student → mentor) and management of the students list (mentor).
- Chat between mentor and student (real time).
- Assignment creation and tracking.
- Session booking with a calendar and slot management.
- Reviews and ratings after sessions.

Addendum: Signal username, meeting and contact-exchange flow (short)
------------------------------------------------------------

- Signal username required at registration
  - Both Student and Mentor must provide a "Signal username" (signal_username) during registration. This field is stored privately and not shown publicly.

- Visibility rules
  - signal_username is hidden by default and becomes visible to the matched counterparty only after a successful meeting and mutual consent.

- Meeting + calendar
  - When a mentorship request is accepted, the system creates an internal meeting and chat and adds a Google Calendar event for both participants (via OAuth) with the meeting link.

- Post-meeting mini-survey
  - After the meeting, both participants receive a short two-question survey:
    1. "Did the meeting take place?" (Yes / No)
    2. "Do you want to continue interaction with this person?" (Yes / No)

- Contact reveal logic
  - signal_username is revealed to both participants only if BOTH answered "Yes" to both questions.
  - If either participant answers "No" to either question (including asymmetric cases), the interaction ends and no contact is revealed.
  - All survey responses are logged with timestamps and meeting IDs.

- Data protection
  - signal_username is stored encrypted. Users can update or delete it in account settings. Admins can view interaction logs for dispute resolution.

```