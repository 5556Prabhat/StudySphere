# StudySphere — Implementation Status & Project Structure

**Last updated:** 20 November 2026, 01:12 IST (Asia/Kolkata)  
**Current phase:** Feature-complete production-ready application with **WhatsApp/Instagram-Style Group Chat & Academic Doubts**, **Collaborate Workspace (Unique Group IDs, `@username` Invitations, Admin Join Approval, Transfer Admin, Leave/Delete Group)**, **Top Navbar Notification ON/OFF Toggle**, **Classy SaaS Auth with Conditional Error Instructions**, **Advanced Leaderboard & Centralized `PointsTransaction` Ledger**, **EdTech SaaS Homepage**, and **Premium SaaS Student Dashboard** — migrated through `hub.0007`, static-collected, and verified with **37 passing automated tests**.

---

## 1. Project Directory Structure

```text
d:\Djangoca2\
├── manage.py
├── requirements.txt
├── Dockerfile
├── .env / .env.example
├── ARCHITECTURE.md          # Complete system & database architecture diagrams (Mermaid)
├── PROJECT_STATUS.md        # Implementation status & delivery log
├── README.md                # Comprehensive developer & user documentation
├── study_platform/
│   ├── __init__.py
│   ├── settings.py          # Automatic .env loader, STORAGES (default + staticfiles), Channels, SMTP, Logging
│   ├── urls.py              # Root URL routing + media serving in DEBUG mode
│   ├── asgi.py              # HTTP + WebSocket ASGI router (Django Channels)
│   └── wsgi.py
├── hub/
│   ├── models.py            # 17 Models: Profile, StudyMaterial, MaterialReview, StudyGroup (with group_code),
│   │                        # GroupMembership, GroupAccessRequest (Join Requests & Invitations),
│   │                        # DiscussionMessage, AcademicDoubt, DoubtReply, LearningProgress,
│   │                        # ContentReport, Notification, StudyCollection, SavedMaterial,
│   │                        # AIUsage, QuizAttempt, PointsTransaction
│   ├── services.py          # Centralized Points Ledger, Doubt Solution Anti-Spam Engine,
│   │                        # Leaderboard & Achievements, AI Studio helper, PDF/DOCX/PPTX extraction, Email OTP
│   ├── signals.py           # Automatic post_save / post_delete PointsTransaction ledger synchronization
│   ├── views.py             # All HTTP views (Home, Dashboard, Library, WhatsApp/Instagram GC, Collaborate Hub,
│   │                        # Group Settings/Transfer/Leave/Delete, Doubts, Leaderboard, Points History,
│   │                        # Navbar Notification Toggle, AI Studio, Auto-Grader, Email OTP Reset, Moderation, Health)
│   ├── forms.py             # CustomLoginForm & SignUpForm (6+ chars + special char validation, zero help_text clutter),
│   │                        # MaterialForm (PDF/PNG/DOCX/PPTX), ReviewForm, GroupForm, MessageForm,
│   │                        # AcademicDoubtForm, DoubtReplyForm, ProfileForm, CollectionForm
│   ├── urls.py              # Application routes (35 named endpoints)
│   ├── consumers.py         # GroupChatConsumer (WebSocket real-time chat + Admin badge + message delete broadcast)
│   ├── routing.py           # WebSocket URL routing (/ws/groups/<id>/)
│   ├── middleware.py        # ErrorLoggingMiddleware
│   ├── context_processors.py# Unread notification count & notifications_enabled toggle state
│   ├── admin.py             # Admin registrations for all models
│   ├── tests.py             # 37 automated unit & integration tests
│   ├── management/commands/
│   │   └── seed_demo.py     # Optional demo data seeder
│   └── migrations/
│       ├── 0001_initial.py
│       ├── 0002_learningprogress_review_due_at_and_more.py
│       ├── 0003_quizattempt.py
│       ├── 0004_profile_avatar_profile_email_notifications.py
│       ├── 0005_alter_studymaterial_material_type.py
│       ├── 0006_discussionmessage_is_system_and_more.py
│       └── 0007_alter_studygroup_options_studygroup_group_code_and_more.py
├── templates/
│   ├── base.html            # Unified layout shell (Topbar with Notification ON/OFF Toggle Switch, Search, Streak)
│   ├── hub/
│   │   ├── home.html        # Interactive EdTech SaaS Landing Page (Typed.js, GSAP ScrollTrigger, 5 Spotlights)
│   │   ├── dashboard.html   # Premium SaaS Student Dashboard (3D Hero, 4 Stat Cards, 4 Quick Access Cards)
│   │   ├── group_detail_v2.html # WhatsApp/Instagram Left/Right Bubble Chat (General Talk & Academic Doubts + Settings Drawer)
│   │   ├── group_list.html  # Clean Collaborate Hub (Create Group with Unique ID | Join Group by ID)
│   │   ├── leaderboard.html # 3-Tab Leaderboard & How to Earn Points Guide
│   │   ├── points_history.html # Centralized Points History Ledger with filters, search, pagination & audit drawer
│   │   ├── material_list.html
│   │   ├── material_detail_v2.html # Resource detail with inline PNG/image preview, reviews & reporting
│   │   ├── ai_studio_v2.html
│   │   ├── quiz_results.html
│   │   ├── saved_materials.html
│   │   ├── notifications.html # Alerts feed with one-click Notification ON/OFF toggle button
│   │   ├── moderation.html
│   │   ├── form_page.html
│   │   └── email/notification.html
│   └── registration/
│       ├── login.html       # Classy frosted-glass SaaS card with conditional error banner
│       ├── signup.html      # Classy frosted-glass SaaS card (instructions hidden unless password invalid)
│       ├── forgot_password.html
│       ├── verify_otp.html
│       └── reset_password.html
└── static/
    └── css/app.css          # Unified Premium SaaS, Auth Stage, Collaborate & WhatsApp/Instagram Chat stylesheet (?v=15)
```

---

## 2. Completed Features Breakdown

### A. WhatsApp / Instagram DM Style Group Chat & Academic Doubts (`templates/hub/group_detail_v2.html`)
- [x] **Left & Right Bubble Messenger Layout:**
  - **Your Own Messages (`.wa-row.is-mine`):** Right-aligned inside a vibrant violet-indigo gradient bubble with white text, bottom-right chat tail, timestamp, delivered ticks (`✓✓`), **Reply**, and **Delete** buttons.
  - **Other Students' Messages (`.wa-row.is-other`):** Left-aligned with circular initial avatar, crisp white chat bubble with bottom-left tail, `@username`, timestamp, and **Reply** button.
  - **Per-Message Delete Button (`POST /messages/<msg_pk>/delete/`):** Allows users to delete their own messages smoothly in place via AJAX (`fetch`) without page reload.
  - **Group Admin Badge (`👑 Admin`):** Automatically displayed next to the Group Admin's `@username` on all General Talk and Academic Doubt messages (including live WebSocket broadcasts).
  - **Zero Instruction Clutter:** Removed redundant badges (`DEFAULT CAMPUS GROUP CHAT...`), form labels (`Body:`), and multi-field forms in favor of a single sleek pill chat composer (`Enter` to send, `Shift+Enter` for newline) across both **General Talk (`0 pts`)** and **Academic Doubts (`+20 pts / Accepted Solution`)**.

### B. Collaborate Workspace & Study Group Lifecycle (`templates/hub/group_list.html`, `hub/views.py`)
- [x] **Create Group with Unique ID (`SS-XXXXXX`):**
  - Fill **Group Name** and **Group Info** to create a private study group with an auto-generated Unique Group ID (`StudyGroup.group_code`).
  - Automatically redirects straight into the created group workspace (`/groups/<pk>/`) where the Unique Group ID is shown in the header with a one-click **Copy** button.
- [x] **Single Active Group Rule:**
  - While a student is a member of a custom group, clicking **Collaborate** (`/groups/`) takes them directly to their active group chat instead of showing the Create/Join forms.
- [x] **Invite by `@username` & Join by Unique ID with Admin Approval (`GroupAccessRequest`):**
  - Group Admin/members can invite peers by `@username` (`POST /groups/<pk>/invite/`), sending an invitation directly to the student's account.
  - Students can enter a group's Unique ID (`POST /groups/join-by-id/`) to send a join request that must be approved by the Group Admin (`POST /group-requests/<req_pk>/respond/`).
- [x] **Group Settings Drawer (`⚙️ Settings`), Transfer Admin, Leave & Delete Group:**
  - **Regular Members:** Can click **Leave Group** (`POST /groups/<pk>/leave/`) anytime to exit and return to the Create/Join page.
  - **Group Admin:** To leave or switch groups, the Admin must either **Transfer Admin** (`POST /groups/<pk>/transfer-admin/`) to another member (or click **Transfer & Leave**) or **Delete Group** (`POST /groups/<pk>/delete/`).

### C. Top Navbar Notification ON/OFF Toggle & Smart Email Filtering
- [x] **Interactive Navbar Notification Pill (`templates/base.html`, `POST /notifications/toggle/`):**
  - Located right next to the streak counter (`🔥`) in the top navbar, pairing the notification bell with a live **ON / OFF** switch (`role="switch"`).
  - Toggles `profile.email_notifications` via AJAX without reloading the page and switches the bell icon between active and muted (slashed bell).
- [x] **Smart Email Filtering:**
  - Random **General Talk** chat messages never send emails (`send_email=False`).
  - Newly shared **PDFs & Study Notes** (`material_create`) send email notifications **only** to users whose notification toggle is **ON** (`email_notifications=True`).

### D. Classy SaaS Authentication & Conditional Password Instructions
- [x] **Clean Login & Sign-Up UI (`templates/registration/login.html`, `signup.html`, `hub/forms.py`):**
  - Cleared all permanent Django `help_text` clutter under Username, Email, and Password fields.
  - Enforces password strength (`>= 6` characters and at least one special character `r"[^A-Za-z0-9]"`), displaying instructions **only** inside an animated error banner (`.auth-error-banner`) when an invalid password is submitted.
  - Styled with floating ambient lavender aura orbs, frosted glass card, top gradient accent bar, and 3D graduation-cap emblem badge.

### E. Centralized `PointsTransaction` Ledger, Anti-Spam Engine & Points History
- [x] **Centralized Point Formula:** Share Notes (`+25`), Solve Academic Doubt (`+20`), Resource Review (`+15`), Complete Material (`+10`), Complete AI Quiz (`+10`), General Talk (`0`).
- [x] **Backend Anti-Abuse Protections:** 1 reward per doubt, no self-answer rewards, 15+ chars & 3+ words minimum explanation, max 5 rewarded solutions (100 pts) per student per day, anti-collusion pair limit, and non-destructive moderator reward revocation.
- [x] **Dedicated Points History (`/points-history/`) & 3-Tab Leaderboard (`/leaderboard/`):** Full transaction audit trail with filters, search, pagination, and expandable details.

---

## 3. How to Run & Test Locally

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py runserver
```

Run the automated test suite (**37 tests**):
```powershell
.\.venv\Scripts\python.exe manage.py test hub -v2
```
