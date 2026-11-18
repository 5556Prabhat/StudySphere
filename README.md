# StudySphere

**StudySphere** is an AI-powered collaborative EdTech SaaS platform built with Django 5.2 and Django Channels. Students can share multi-format study notes (`PDF`, `PNG`, `DOCX`, `PPTX`, `MD`), collaborate in a two-tab real-time Group Chat (**General Talk** & **Academic Doubts**), generate summaries and auto-graded quizzes in **AI Study Studio**, schedule spaced-repetition reviews, and track their academic contributions on the **Campus Leaderboard** and **Points History Ledger**.

---

## Quick Start (Windows PowerShell)

```powershell
# 1. Run migrations
.\.venv\Scripts\python.exe manage.py migrate

# 2. Collect static files
.\.venv\Scripts\python.exe manage.py collectstatic --noinput

# 3. Start the development server
.\.venv\Scripts\python.exe manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.
- **Student Dashboard:** `http://127.0.0.1:8000/dashboard/`
- **Global Doubt & Study Lounge (Default GC):** `http://127.0.0.1:8000/global-chat/`
- **Campus Leaderboard & How to Earn Points:** `http://127.0.0.1:8000/leaderboard/`
- **Personal Points History Ledger:** `http://127.0.0.1:8000/points-history/`
- **AI Study Studio:** `http://127.0.0.1:8000/ai-studio/`
- **System Health Check:** `http://127.0.0.1:8000/health/`

*(Optional: Run `.\.venv\Scripts\python.exe manage.py seed_demo` if you want to populate sample accounts and resources.)*

---

## Key Platform Capabilities

### 1. Two-Tab Group Chat & Academic Doubt Reward System
- **Tab A — General Talk (`0 pts`):** Real-time WebSocket and HTTP group chat with quote-replies (`reply_to`), avatars, and timestamps. Casual chat messages earn `0` points so leaderboard rankings cannot be spammed.
- **Tab B — Academic Doubts (`+20 pts / Accepted Solution`):** Structured Q&A forum where students post doubts with a title, subject, and `@username` tag. When the question author (or a moderator) accepts a peer's explanation as the solution, the solver earns **`+20 pts`**.
- **Anti-Spam & Anti-Abuse Rules:** Enforces 1 reward per doubt, no self-answer rewards, minimum explanation length (15+ chars & 3+ distinct words), a daily cap of **5 rewarded solutions (100 pts/day)**, anti-collusion pair limits, and moderator reward revocation.

### 2. Centralized `PointsTransaction` Ledger & Points History (`/points-history/`)
Every point award or deduction is recorded in `PointsTransaction` with a unique idempotent `transaction_key`:

| Activity | Points | Condition |
| :--- | :---: | :--- |
| **Share Study Notes** (`NOTE_SHARED`) | **`+25`** | Published and approved (`PDF`, `PNG`, `DOCX`, `PPTX`, `MD`, or link) |
| **Solve Academic Doubt** (`DOUBT_SOLVED`) | **`+20`** | Accepted solution in Academic Doubts |
| **Resource Review** (`RESOURCE_REVIEW`) | **`+15`** | Valid 1–5 star rating and review |
| **Complete Study Material** (`MATERIAL_COMPLETED`) | **`+10`** | Marked complete (schedules spaced repetition `1 → 2 → 4 → 60` days) |
| **Complete AI Quiz** (`QUIZ_COMPLETED`) | **`+10`** | Valid completed quiz attempt in AI Studio |
| **General Talk Message** | **`0`** | Casual chat messages do not award points |

Students can filter, search, paginate, and inspect every transaction (including revoked rewards and moderator reasons) on `/points-history/`.

### 3. AI Study Studio & Document Extraction (`/ai-studio/`)
- Automatically extracts text from uploaded `PDF`, `DOCX`, `PPTX`, `TXT`, and `MD` files.
- Generates **Concise Summaries**, **Important Questions**, **Simple Explanations**, and **Auto-Graded Multiple-Choice Quizzes**.
- Works out of the box with a local privacy-preserving processor and automatically upgrades to OpenAI when `OPENAI_API_KEY` is configured.

### 4. Email OTP Password Recovery & Notifications
- Configure `EMAIL_HOST_USER` and a 16-character Google App Password in `EMAIL_HOST_PASSWORD` inside [`.env`](.env) to send real 6-digit password-reset OTPs (`/accounts/forgot-password/`) and HTML activity emails via Gmail SMTP.

---

## Running Automated Tests

All **34 unit and integration tests** in [hub/tests.py](hub/tests.py) can be executed with:

```powershell
.\.venv\Scripts\python.exe manage.py test hub -v2
```

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the full architecture and delivery log.
