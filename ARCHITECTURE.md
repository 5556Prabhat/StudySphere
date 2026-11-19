# StudySphere — System Architecture & Technical Design

**StudySphere** is a full-stack, real-time collaborative EdTech SaaS platform built on **Django 5.2**, **Django Channels (ASGI / Daphne)**, **SQLite / Redis**, and a dual-mode **AI Study Studio** (OpenAI + privacy-preserving local processor).

---

## 1. High-Level Layered System Architecture

StudySphere uses a **dual-protocol ASGI architecture** (`study_platform/asgi.py`) that routes standard HTTP requests through the Django WSGI/ASGI view layer and persistent full-duplex WebSocket connections (`/ws/groups/<id>/`) through `AuthMiddlewareStack` and `GroupChatConsumer`.

```mermaid
flowchart TD
    subgraph ClientLayer["1. Client & Presentation Layer (Browser)"]
        LP["EdTech SaaS Landing Page (/)\nGSAP ScrollTrigger + Typed.js"]
        DASH["Premium SaaS Student Workspace (/dashboard/)\nInter UI + Ctrl+K Search + Streak Tracker"]
        GCUI["Two-Tab Group Chat UI\nTab A: General Talk (0 pts) | Tab B: Academic Doubts (+20 pts)"]
        AIUI["AI Study Studio & Interactive Auto-Graded Quiz UI"]
        PHUI["3-Tab Leaderboard & Points History Audit Dashboard"]
    end

    subgraph GatewayLayer["2. ASGI Protocol Router & Middleware Layer (Daphne)"]
        ASGI["ProtocolTypeRouter (study_platform/asgi.py)"]
        SEC["SecurityMiddleware + WhiteNoiseMiddleware + CsrfViewMiddleware"]
        AUTHMW["AuthenticationMiddleware / Channels AuthMiddlewareStack"]
        ERRMW["ErrorLoggingMiddleware (hub/middleware.py)"]
    end

    subgraph AppLayer["3. Application & Business Logic Layer (hub/)"]
        VIEWS["HTTP Views (hub/views.py)\n30+ Views & Form Controllers"]
        WS["AsyncWebsocketConsumer (hub/consumers.py)\nGroupChatConsumer"]
        SERVICES["Core Domain Services (hub/services.py)"]
        SIGNALS["Model Signals (hub/signals.py)\nAuto-Profile & Ledger Sync"]
    end

    subgraph DomainEngines["4. Specialized Domain Engines"]
        LEDGER["Centralized Points Ledger & Anti-Spam Engine\naward_points() / accept_doubt_solution() / revoke_points()"]
        EXTRACT["Multi-Format Document Extractor\npypdf (PDF) + python-docx (DOCX) + python-pptx (PPTX)"]
        AIENG["AI Learning Assistant & Quiz Auto-Grader\nOpenAI Responses API + Local Deterministic Fallback"]
        OTPENG["3-Step Email OTP & Notification Service\nGmail SMTP / Console Backend"]
    end

    subgraph DataLayer["5. Persistence & Infrastructure Layer"]
        DB[("SQLite / Relational DB\n16 Normalized Models")]
        MEDIA[("FileSystemStorage (media/)\nPDF, PNG, DOCX, PPTX, Avatars")]
        CHLAYER[("Channel Layer\nRedis / InMemoryChannelLayer")]
        LOGS[("Rotating File & Console Logs\nlogs/studysphere.log")]
    end

    LP & DASH & GCUI & AIUI & PHUI -->|"HTTP / HTTPS"| ASGI
    GCUI <-->|"WebSocket (ws/wss)"| ASGI
    ASGI -->|"http"| SEC --> AUTHMW --> ERRMW --> VIEWS
    ASGI -->|"websocket"| AUTHMW --> WS
    VIEWS --> SERVICES
    VIEWS --> SIGNALS
    WS <--> CHLAYER
    WS --> DB
    SERVICES --> LEDGER & EXTRACT & AIENG & OTPENG
    SIGNALS --> LEDGER
    LEDGER & EXTRACT & AIENG --> DB
    VIEWS --> MEDIA
    ERRMW --> LOGS
```

---

## 2. Database Entity-Relationship Architecture (16 Models)

All domain entities reside in `hub/models.py` and are migrated through `hub.0006_discussionmessage_is_system_and_more`.

```mermaid
erDiagram
    USER ||--|| PROFILE : "has one"
    USER ||--o{ STUDY_MATERIAL : "uploads (owner)"
    USER ||--o{ MATERIAL_REVIEW : "authors"
    USER ||--o{ STUDY_GROUP : "owns"
    USER ||--o{ GROUP_MEMBERSHIP : "joins"
    USER ||--o{ DISCUSSION_MESSAGE : "posts (General Talk)"
    USER ||--o{ ACADEMIC_DOUBT : "asks / solves"
    USER ||--o{ DOUBT_REPLY : "explains"
    USER ||--o{ POINTS_TRANSACTION : "earns / deducts"
    USER ||--o{ LEARNING_PROGRESS : "tracks"
    USER ||--o{ SAVED_MATERIAL : "bookmarks"
    USER ||--o{ STUDY_COLLECTION : "organizes"
    USER ||--o{ QUIZ_ATTEMPT : "completes"
    USER ||--o{ AI_USAGE : "consumes"
    USER ||--o{ NOTIFICATION : "receives"
    USER ||--o{ CONTENT_REPORT : "reports"

    STUDY_MATERIAL ||--o{ MATERIAL_REVIEW : "receives"
    STUDY_MATERIAL ||--o{ LEARNING_PROGRESS : "scheduled in"
    STUDY_MATERIAL ||--o{ SAVED_MATERIAL : "saved in"
    STUDY_MATERIAL ||--o{ CONTENT_REPORT : "flagged by"

    STUDY_COLLECTION ||--o{ SAVED_MATERIAL : "contains"

    STUDY_GROUP ||--o{ GROUP_MEMBERSHIP : "enrolls"
    STUDY_GROUP ||--o{ DISCUSSION_MESSAGE : "hosts General Talk"
    STUDY_GROUP ||--o{ ACADEMIC_DOUBT : "hosts Academic Doubts"

    ACADEMIC_DOUBT ||--o{ DOUBT_REPLY : "has threaded replies"
    ACADEMIC_DOUBT ||--o| DOUBT_REPLY : "accepted_reply"

    POINTS_TRANSACTION {
        string transaction_key UK "Unique idempotency key"
        string activity_type "NOTE_SHARED | DOUBT_SOLVED | etc."
        int points "+25 | +20 | +15 | +10 | -20"
        string status "approved | pending | revoked"
        json metadata "Audit details (doubt, subject, asker)"
        string revoked_reason "Moderator revocation reason"
    }
```

---

## 3. Academic Doubt Reward (+20 pts) & Anti-Spam Ledger Flow

To prevent chat-spam score inflation, **General Talk** (`DiscussionMessage`) awards **0 points**, while **Academic Doubts** (`AcademicDoubt` + `DoubtReply`) award **+20 points** strictly when a valid solution is accepted through `accept_doubt_solution()` in `hub/services.py`.

```mermaid
sequenceDiagram
    autonumber
    actor Asker as "Student A (Doubt Author)"
    actor Solver as "Student B (Peer Solver)"
    participant View as "Django View (hub/views.py)"
    participant Engine as "accept_doubt_solution() (hub/services.py)"
    participant Ledger as "PointsTransaction Ledger (DB)"
    actor Mod as "Staff Moderator"

    Asker->>View: POST /groups/<id>/doubts/new/ (Title, Subject, @tag, Body)
    View->>Ledger: 0 Points Awarded (Asking is free)
    Solver->>View: POST /doubts/<id>/reply/ (Detailed Explanation)
    View->>Ledger: 0 Points Awarded (Unaccepted reply = 0 pts)

    Asker->>View: POST /doubts/<id>/accept/<reply_id>/
    View->>Engine: Enter transaction.atomic() + select_for_update()

    Engine->>Engine: 1. Verify Asker == doubt.author (or Staff)
    Engine->>Engine: 2. Verify doubt not already resolved & key not in Ledger
    Engine->>Engine: 3. Verify Solver != Asker (No self-answer reward)
    Engine->>Engine: 4. Verify reply >= 15 chars & >= 3 distinct words & unflagged
    Engine->>Engine: 5. Verify Solver < 5 doubt rewards (< 100 pts) today
    Engine->>Engine: 6. Verify Asker->Solver pair rewards < 2 today (Anti-collusion)

    Engine->>Ledger: Create PointsTransaction (DOUBT_SOLVED, +20 pts, status=approved)
    Engine-->>Asker: Mark Doubt Resolved & Notify Solver (+20 pts!)

    opt Moderator Revokes Fraudulent Solution
        Mod->>View: POST /doubts/<id>/revoke-reward/ (reason)
        View->>Ledger: Mark original transaction status="revoked" (kept in history)
        View->>Ledger: Append REWARD_REVOKED transaction (-20 pts, reason)
    end
```

---

## 4. Centralized Points & Ranking Architecture

Every point change in StudySphere flows through the centralized `PointsTransaction` ledger via `hub/services.py` and `hub/signals.py`:

| Activity Type | Trigger / Signal | Points | Idempotency Key Format |
| :--- | :--- | :---: | :--- |
| **`NOTE_SHARED`** | `StudyMaterial` saved (`is_published=True, is_flagged=False`) | **`+25`** | `NOTE_SHARED:StudyMaterial:<id>` |
| **`DOUBT_SOLVED`** | `accept_doubt_solution()` verified acceptance | **`+20`** | `DOUBT_SOLVED:AcademicDoubt:<id>` |
| **`RESOURCE_REVIEW`** | `MaterialReview` created | **`+15`** | `RESOURCE_REVIEW:MaterialReview:<id>` |
| **`MATERIAL_COMPLETED`** | `LearningProgress.completed = True` | **`+10`** | `MATERIAL_COMPLETED:LearningProgress:<id>` |
| **`QUIZ_COMPLETED`** | `QuizAttempt` created in AI Studio | **`+10`** | `QUIZ_COMPLETED:QuizAttempt:<id>` |
| **`REWARD_REVOKED`** | Staff moderation hide or reward revocation | **`-10` to `-25`** | `REWARD_REVOKED:PointsTransaction:<orig_id>` |
| **`ADMIN_ADJUSTMENT`** | Staff manual point adjustment with reason | **`±N`** | `ADMIN_ADJUSTMENT:<user_id>:<uuid>` |

---

## 5. AI Study Studio & Multi-Format Document Extraction Pipeline

```mermaid
flowchart LR
    UP["User Uploads File\n(PDF, PNG, DOCX, PPTX, TXT, MD)"] --> VAL["MaterialForm Validation\n(<= 15 MB, allowed extensions)"]
    VAL --> EXT["extract_text_from_upload()\n(pypdf / python-docx / python-pptx)"]
    EXT --> DBMAT[("StudyMaterial.extracted_text\n(up to 50,000 chars)")]
    DBMAT --> STUDIO["AI Study Studio (/ai-studio/)\nSelect Resource or Paste Text"]
    STUDIO --> LIMIT{"Daily Limit Check\n(< AI_DAILY_REQUEST_LIMIT)"}
    LIMIT -->|"Allowed"| KEY{"OPENAI_API_KEY\nConfigured?"}
    KEY -->|"Yes"| OAI["OpenAI Responses API\n(gpt-4.1-mini)"]
    KEY -->|"No / Error"| LOC["Local Privacy-Preserving\nStudy Processor"]
    OAI & LOC --> MODE{"Selected Mode"}
    MODE -->|"Summary / Questions / Explain"| OUT["Rendered Study Aid\n+ AIUsage Record"]
    MODE -->|"Practice Quiz (JSON)"| QUIZ["Interactive Radio-Button Quiz"]
    QUIZ --> GRADE["grade_quiz_view (/quiz-grade/)\nAuto-Grades & Saves QuizAttempt (+10 pts)"]
```

---

## 6. Security, Authentication & Observability Architecture

1. **Authentication & 3-Step Email OTP Recovery:**
   - Standard session authentication (`signup`, `login`, `logout`) paired with a 3-step Email OTP recovery flow (`/accounts/forgot-password/` → `/accounts/verify-otp/` → `/accounts/reset-password/`).
   - Generates a 6-digit OTP via `secrets.randbelow(900000) + 100000` with a 10-minute session TTL and a 5-attempt brute-force lock.
   - Automatic `.env` loader in `study_platform/settings.py` switches from console email output to live Gmail SMTP (`django.core.mail.backends.smtp.EmailBackend`) as soon as `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are set.
2. **Access Control & Privacy Isolation:**
   - Group messages and doubts are gated by `GroupMembership` (with automatic enrollment for the default `Global Doubt & Study Lounge`).
   - `/points-history/` strictly scopes queries to `request.user` and returns `403 HttpResponseForbidden` if a student attempts to inspect or modify another student's ledger.
   - `/moderation/`, `/doubts/<id>/revoke-reward/`, `/transactions/<id>/revoke/`, and `/points/adjust/` enforce `request.user.is_staff`.
3. **Observability & Production Hardening:**
   - `ErrorLoggingMiddleware` logs unhandled exceptions with user context and stack traces to `logs/studysphere.log`.
   - `/health/` executes a live `SELECT 1` database check for container/load-balancer health probes.
   - Production mode (`DJANGO_DEBUG=false`) enables HSTS, secure cookies, SSL redirect, and WhiteNoise compressed manifest static storage.
