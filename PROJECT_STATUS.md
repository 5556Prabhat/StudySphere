# StudySphere — Implementation Status & Project Structure

**Last updated:** 18 November 2026, 15:16 IST (Asia/Kolkata)  
**Current phase:** Feature-complete application with **Advanced Leaderboard, Academic Doubt Reward (+20 pts), Centralized `PointsTransaction` Ledger & Points History Dashboard**, **EdTech SaaS Homepage Redesign**, and **Premium SaaS Student Workspace** — locally migrated through `hub.0006`, static-collected, and verified with **34 passing automated tests**.

---

## 1. Project Directory Structure

```text
d:\Djangoca2\
├── manage.py
├── requirements.txt
├── Dockerfile
├── .env / .env.example
├── PROJECT_STATUS.md
├── README.md
├── study_platform/
│   ├── __init__.py
│   ├── settings.py          # Automatic .env loader, STORAGES (default + staticfiles), Channels, SMTP, Logging
│   ├── urls.py              # Root URL routing + media serving in DEBUG mode
│   ├── asgi.py              # HTTP + WebSocket ASGI router (Django Channels)
│   └── wsgi.py
├── hub/
│   ├── models.py            # Profile, StudyMaterial, MaterialReview, StudyGroup, GroupMembership,
│   │                        # DiscussionMessage, AcademicDoubt, DoubtReply, LearningProgress,
│   │                        # ContentReport, Notification, StudyCollection, SavedMaterial,
│   │                        # AIUsage, QuizAttempt, PointsTransaction
│   ├── services.py          # Centralized Points Ledger, Doubt Solution Anti-Spam Engine,
│   │                        # Leaderboard & Achievements, AI Studio helper, PDF/DOCX/PPTX extraction, Email OTP
│   ├── signals.py           # Automatic post_save / post_delete PointsTransaction ledger synchronization
│   ├── views.py             # All HTTP views (Home, Dashboard, Library, Two-Tab GC, Doubts, Leaderboard,
│   │                        # Points History, AI Studio, Auto-Grader, Email OTP Reset, Moderation, Health)
│   ├── forms.py             # SignUpForm, MaterialForm (PDF/PNG/DOCX/PPTX), ReviewForm, GroupForm,
│   │                        # MessageForm, AcademicDoubtForm, DoubtReplyForm, ProfileForm, CollectionForm
│   ├── urls.py              # Application routes
│   ├── consumers.py         # GroupChatConsumer (WebSocket real-time chat)
│   ├── routing.py           # WebSocket URL routing (/ws/groups/<id>/)
│   ├── middleware.py        # ErrorLoggingMiddleware
│   ├── context_processors.py# Unread notification count context processor
│   ├── admin.py             # Admin registrations for all 16 models
│   ├── tests.py             # 34 automated unit & integration tests
│   ├── management/commands/
│   │   └── seed_demo.py     # Optional demo data seeder
│   └── migrations/
│       ├── 0001_initial.py
│       ├── 0002_learningprogress_review_due_at_and_more.py
│       ├── 0003_quizattempt.py
│       ├── 0004_profile_avatar_profile_email_notifications.py
│       ├── 0005_alter_studymaterial_material_type.py
│       └── 0006_discussionmessage_is_system_and_more.py
├── templates/
│   ├── base.html            # Unified layout shell (EdTech SaaS Navbar/Footer on Home + Sidebar/Topbar on Workspace)
│   ├── hub/
│   │   ├── home.html        # Interactive EdTech SaaS Landing Page (Typed.js, GSAP ScrollTrigger, 5 Spotlights)
│   │   ├── dashboard.html   # Premium SaaS Student Dashboard (3D Hero, 4 Stat Cards, 4 Quick Access Cards)
│   │   ├── group_detail_v2.html # Two-Tab Group Chat (Tab A: General Talk 0 pts | Tab B: Academic Doubts +20 pts)
│   │   ├── leaderboard.html # 3-Tab Leaderboard & How to Earn Points Guide
│   │   ├── points_history.html # Centralized Points History Ledger with filters, search, pagination & audit drawer
│   │   ├── material_list.html
│   │   ├── material_detail_v2.html # Resource detail with inline PNG/image preview, reviews & reporting
│   │   ├── ai_studio_v2.html
│   │   ├── quiz_results.html
│   │   ├── group_list.html
│   │   ├── saved_materials.html
│   │   ├── notifications.html
│   │   ├── moderation.html
│   │   ├── form_page.html
│   │   └── email/notification.html
│   └── registration/
│       ├── login.html
│       ├── signup.html
│       ├── forgot_password.html
│       ├── verify_otp.html
│       └── reset_password.html
└── static/
    └── css/app.css          # Unified Premium SaaS & EdTech Landing Page stylesheet
```

---

## 2. Completed Features Breakdown

### A. Advanced Leaderboard, Academic Doubt Reward & Points History System
- [x] **Two-Tab Group Chat (`templates/hub/group_detail_v2.html`):**
  - **Tab A — General Talk (`0 pts`):** Casual real-time WebSocket and HTTP messaging with quote-replies (`reply_to`), user avatars, and timestamps. Awards **0 points** per message to prevent chat spam.
  - **Tab B — Academic Doubts (`+20 pts / Accepted Solution`):** Dedicated academic Q&A forum inside every Study Group and the Default Global GC (`AcademicDoubt` and `DoubtReply` models) supporting doubt title, subject/category, `@username` tagging, threaded explanations, resolved/unresolved status badges, and solver attribution.
- [x] **Backend Anti-Spam & Anti-Abuse Protections (`accept_doubt_solution()` in `hub/services.py`):**
  - Enforced inside `transaction.atomic()` with `select_for_update()` row locking:
    1. Only 1 accepted solution reward per academic doubt (`unique` `transaction_key`).
    2. No self-answer rewards (`reply.author != doubt.author`).
    3. Asking a doubt or posting unaccepted replies awards `0 pts`.
    4. Minimum explanation quality check (`>= 15` characters and `>= 3` distinct words; unflagged).
    5. Daily cap of **max 5 rewarded solutions** (**100 doubt-solving points**) per student per day.
    6. Anti-collusion rate limit preventing repeated rewards between the same two students on the same day.
    7. Staff moderation endpoints to revoke flagged rewards (`/doubts/<id>/revoke-reward/`, `/transactions/<id>/revoke/`) or record authorized adjustments (`/points/adjust/`) with a mandatory reason.
- [x] **Centralized `PointsTransaction` Ledger & Point Formula:**
  - **Share Approved Study Notes (`NOTE_SHARED`):** `+25 pts`
  - **Write Valid Resource Review (`RESOURCE_REVIEW`):** `+15 pts`
  - **Solve Accepted Academic Doubt (`DOUBT_SOLVED`):** `+20 pts`
  - **Complete Study Material (`MATERIAL_COMPLETED`):** `+10 pts`
  - **Complete AI Quiz (`QUIZ_COMPLETED`):** `+10 pts`
  - **General Talk Messages:** `0 pts`
  - Every award and revocation is recorded permanently in `PointsTransaction` (revocations mark the original entry `revoked` and append a negative `REWARD_REVOKED` reversal entry so historical records are never deleted).
- [x] **Points History Page (`/points-history/`) & 3-Tab Leaderboard (`/leaderboard/`):**
  - Tabs for **Leaderboard**, **How to Earn Points**, and **Points History**.
  - Summary cards (*Total Points*, *Points Earned*, *Points Deducted*, *Total Contributions*), filterable/searchable paginated transaction table, clickable audit detail rows, primary badges (*👑 Grandmaster Mentor*, *📚 Top Note Sharer*, *💡 Doubt Solver*, *🚀 Active Scholar*), and separate achievement badges (*🏅 Problem Solver*, *📖 Knowledge Contributor*, *🔥 Consistent Learner*, *🌟 Campus Legend*).

### B. EdTech SaaS Homepage & Premium SaaS Student Dashboard
- [x] **EdTech SaaS Homepage (`/`, `templates/hub/home.html`):**
  - Sticky navigation bar with scroll-spy, Hero section with **Typed.js** typewriter animation and 3D graduation cap & books illustration, **GSAP ScrollTrigger** pinned horizontal-scrolling 6-card feature showcase, interactive 4-step workflow timeline, 5 alternating product spotlight showcases, animated database counters, peer reviews, and a 4-column SaaS footer.
- [x] **Premium SaaS Dashboard (`/dashboard/`, `templates/hub/dashboard.html`):**
  - Persistent Left Sidebar (`.saas-sidebar`) without promotional clutter, Top Search/Streak/Notification bar (`Ctrl + K` shortcut), 3D Hero banner, 4 live Statistic Cards, and 4 Quick Access Cards.

### C. Core Platform, File Uploads & Email OTP Security
- [x] **Multi-Format Resource Sharing & Extraction:** Supports `PDF`, `PNG`/`JPG`/`WebP` (with inline image preview), `DOCX`, `PPTX`, `TXT`, and `MD` uploads up to 15 MB (`STORAGES` configured with both `default` and `staticfiles`), plus automatic text extraction for AI Studio.
- [x] **3-Step Email OTP Forgot-Password Flow:** `/accounts/forgot-password/` → `/accounts/verify-otp/` → `/accounts/reset-password/` with automatic `.env` loading and Gmail SMTP switching.
- [x] **Automated Test Suite:** **34 tests passing** in `hub/tests.py`.

---

## 3. How to Run & Test Locally

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Run the automated test suite:
```powershell
.\.venv\Scripts\python.exe manage.py test hub -v2
```
