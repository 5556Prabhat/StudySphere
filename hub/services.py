from datetime import timedelta
from io import BytesIO
import json
import re
import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, models, transaction
from django.template.loader import render_to_string
from django.utils import timezone


# ---------------------------------------------------------------------------
# Reward Point Constants & Anti-Abuse Limits
# ---------------------------------------------------------------------------

POINTS_NOTE_SHARED = 25
POINTS_RESOURCE_REVIEW = 15
POINTS_DOUBT_SOLVED = 20
POINTS_MATERIAL_COMPLETED = 10
POINTS_QUIZ_COMPLETED = 10
POINTS_GENERAL_TALK = 0

MAX_DAILY_DOUBT_REWARDS = 5
MAX_DAILY_DOUBT_POINTS = 100
MAX_SAME_PAIR_DAILY_REWARDS = 2
MIN_DOUBT_SOLUTION_CHARS = 15
MIN_DOUBT_SOLUTION_WORDS = 3


# ---------------------------------------------------------------------------
# Text extraction from uploads
# ---------------------------------------------------------------------------

def extract_text_from_upload(uploaded_file):
    """Extract text from text, PDF, DOCX, or PPTX uploads; returns '' for others."""
    name = uploaded_file.name.lower()
    try:
        if name.endswith((".txt", ".md")):
            return uploaded_file.read().decode("utf-8", errors="replace")[:50_000]
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(uploaded_file.read()))
            return "\n".join(page.extract_text() or "" for page in reader.pages)[:50_000]
        if name.endswith((".doc", ".docx")):
            return _extract_docx(uploaded_file)
        if name.endswith((".ppt", ".pptx")):
            return _extract_pptx(uploaded_file)
    except Exception:
        return ""
    return ""


def _extract_docx(uploaded_file):
    """Extract paragraph text from a DOCX file."""
    from docx import Document
    doc = Document(BytesIO(uploaded_file.read()))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    paragraphs.append(text)
    return "\n".join(paragraphs)[:50_000]


def _extract_pptx(uploaded_file):
    """Extract text from all slides of a PPTX file."""
    from pptx import Presentation
    prs = Presentation(BytesIO(uploaded_file.read()))
    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        texts.append(text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        text = cell.text.strip()
                        if text:
                            texts.append(text)
    return "\n".join(texts)[:50_000]


# ---------------------------------------------------------------------------
# Email notification helper
# ---------------------------------------------------------------------------

def send_notification_email(user, subject, text, link=""):
    """Send a notification email to a user if they have email notifications enabled
    and an email address on file. Fails silently to never block the request."""
    try:
        if not user.email:
            return
        profile = getattr(user, "profile", None)
        if profile and not profile.email_notifications:
            return
        html_body = render_to_string("hub/email/notification.html", {
            "username": user.username,
            "text": text,
            "link": link,
            "site_name": "StudySphere",
        })
        send_mail(
            subject=f"[StudySphere] {subject}",
            message=text,
            from_email=None,
            recipient_list=[user.email],
            html_message=html_body,
            fail_silently=True,
        )
    except Exception:
        pass


def send_password_reset_otp_email(user, otp_code):
    """Send a 6-digit password reset OTP to the user's email address.
    Returns (True, '') on success or (False, error_message) on SMTP failure."""
    text = (
        f"Hi {user.username},\n\n"
        f"Your StudySphere 6-digit password reset OTP is: {otp_code}\n\n"
        f"This code is valid for 10 minutes. If you did not request a password reset, you can ignore this email."
    )
    html_body = render_to_string("hub/email/notification.html", {
        "username": user.username,
        "text": f"Your 6-digit password reset OTP is: {otp_code} (valid for 10 minutes).",
        "link": "",
        "site_name": "StudySphere",
    })
    try:
        send_mail(
            subject=f"[StudySphere] Password Reset OTP: {otp_code}",
            message=text,
            from_email=None,
            recipient_list=[user.email],
            html_message=html_body,
            fail_silently=False,
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# AI learning assistant
# ---------------------------------------------------------------------------

def local_learning_assist(text, action):
    """Small local-first AI placeholder; replace with a managed AI provider in production."""
    clean = " ".join(text.split())
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    sentences = [s for s in sentences if len(s) > 12]
    if action == "summary":
        return " ".join(sentences[:3]) or "Add a little more source text to create a summary."
    if action == "questions":
        seeds = sentences[:5] or [clean]
        return "\n".join(f"{index + 1}. What is the key idea in: {sentence[:130]}?" for index, sentence in enumerate(seeds))
    if action == "quiz":
        return _generate_local_quiz(sentences, clean)
    return "Break the topic into its definition, key steps, a worked example, and one common mistake. Start with: " + (sentences[0] if sentences else clean)


def _generate_local_quiz(sentences, clean):
    """Generate a structured quiz with questions and answers for auto-grading."""
    seeds = sentences[:5] or [clean]
    quiz_items = []
    for i, sentence in enumerate(seeds):
        quiz_items.append({
            "question": f"Q{i + 1}. Explain or apply this idea: {sentence[:120]}",
            "choices": [
                f"A) It relates to {sentence[:40]}",
                f"B) It describes {sentence[20:60] if len(sentence) > 20 else sentence[:40]}",
                f"C) It is unrelated to the topic",
                f"D) None of the above",
            ],
            "answer": "A",
            "explanation": f"The correct answer relates to the key idea: {sentence[:80]}",
        })
    return json.dumps(quiz_items)


def parse_quiz_result(quiz_json):
    """Parse a quiz JSON string into a list of question dicts."""
    try:
        return json.loads(quiz_json)
    except (json.JSONDecodeError, TypeError):
        return []


def grade_quiz(quiz_data, user_answers):
    """Grade a quiz given the structured data and user answers.
    Returns (score_percent, total, correct, results_list)."""
    total = len(quiz_data)
    if total == 0:
        return 0, 0, 0, []
    correct = 0
    results = []
    for i, item in enumerate(quiz_data):
        user_answer = user_answers.get(str(i), "").strip().upper()
        is_correct = user_answer == item.get("answer", "").strip().upper()
        if is_correct:
            correct += 1
        results.append({
            "question": item["question"],
            "choices": item.get("choices", []),
            "correct_answer": item.get("answer", ""),
            "user_answer": user_answer,
            "is_correct": is_correct,
            "explanation": item.get("explanation", ""),
        })
    score_percent = round((correct / total) * 100)
    return score_percent, total, correct, results


def learning_assist(text, action):
    """Use OpenAI when configured, falling back to a local privacy-preserving helper."""
    if not settings.OPENAI_API_KEY:
        return local_learning_assist(text, action), "local"
    instructions = {
        "summary": "Create a clear, concise study summary using headings and bullets.",
        "questions": "Generate 5 important short-answer study questions from this source.",
        "explain": "Explain this topic simply, with an analogy and a concrete example.",
        "quiz": (
            "Create a 5-question multiple-choice quiz from this source material. "
            "Return ONLY valid JSON — an array of objects, each with keys: "
            '"question" (string), "choices" (array of 4 strings like "A) …", "B) …", "C) …", "D) …"), '
            '"answer" (single letter A/B/C/D), and "explanation" (string). '
            "No extra text before or after the JSON."
        ),
    }
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions="You are a careful educational study assistant. Do not invent facts not present in the source. " + instructions.get(action, instructions["summary"]),
            input=text[:50_000],
        )
        return response.output_text, "openai"
    except Exception:
        return local_learning_assist(text, action), "local-fallback"


# ---------------------------------------------------------------------------
# Centralized Points Ledger & Academic Doubt Reward Engine
# ---------------------------------------------------------------------------

def award_points(
    user,
    activity_type,
    points,
    description,
    related_object_type="",
    related_object_id=None,
    transaction_key=None,
    metadata=None,
    status="approved",
):
    """Idempotently record a points award in the centralized PointsTransaction ledger.
    Uses a unique transaction_key and transaction.atomic() to prevent duplicate rewards."""
    from .models import PointsTransaction

    if not user or not getattr(user, "pk", None):
        return None, False

    key = transaction_key or f"{activity_type}:{related_object_type}:{related_object_id}"
    try:
        with transaction.atomic():
            tx, created = PointsTransaction.objects.get_or_create(
                transaction_key=key,
                defaults={
                    "user": user,
                    "activity_type": activity_type,
                    "description": description[:300],
                    "points": int(points),
                    "related_object_type": related_object_type,
                    "related_object_id": related_object_id,
                    "metadata": metadata or {},
                    "status": status,
                },
            )
            return tx, created
    except IntegrityError:
        tx = PointsTransaction.objects.filter(transaction_key=key).first()
        return tx, False


def revoke_points_transaction(tx, reason="Flagged or revoked by moderator", moderator=None):
    """Revoke an existing positive PointsTransaction without deleting the historical record.
    Marks the original transaction as revoked and creates a negative REWARD_REVOKED ledger entry."""
    from .models import AcademicDoubt, PointsTransaction

    if not tx:
        return None, False

    with transaction.atomic():
        locked_tx = PointsTransaction.objects.select_for_update().get(pk=tx.pk)
        if locked_tx.points <= 0 or locked_tx.status == PointsTransaction.Status.REVOKED:
            return None, False

        now = timezone.now()
        clean_reason = (reason or "Revoked by moderator").strip()[:300]
        locked_tx.status = PointsTransaction.Status.REVOKED
        locked_tx.revoked_at = now
        locked_tx.revoked_reason = clean_reason
        locked_tx.save(update_fields=["status", "revoked_at", "revoked_reason", "updated_at"])

        if locked_tx.related_object_type == "AcademicDoubt" and locked_tx.related_object_id:
            AcademicDoubt.objects.filter(pk=locked_tx.related_object_id).update(reward_revoked=True)

        reversal_key = f"REWARD_REVOKED:PointsTransaction:{locked_tx.pk}"
        rev_meta = dict(locked_tx.metadata or {})
        rev_meta.update({
            "original_transaction_id": locked_tx.pk,
            "original_activity_type": locked_tx.activity_type,
            "revoked_by": getattr(moderator, "username", "moderator") if moderator else "system",
            "revoked_reason": clean_reason,
        })
        reversal_tx, created = PointsTransaction.objects.get_or_create(
            transaction_key=reversal_key,
            defaults={
                "user": locked_tx.user,
                "activity_type": PointsTransaction.ActivityType.REWARD_REVOKED,
                "description": f"Revoked: {locked_tx.description}"[:300],
                "points": -abs(locked_tx.points),
                "related_object_type": locked_tx.related_object_type,
                "related_object_id": locked_tx.related_object_id,
                "metadata": rev_meta,
                "status": PointsTransaction.Status.REVOKED,
                "revoked_at": now,
                "revoked_reason": clean_reason,
            },
        )
        return reversal_tx, created


def revoke_points_for_object(related_object_type, related_object_id, reason="Revoked by moderation", moderator=None):
    """Find any approved positive reward for the given related object and revoke it."""
    from .models import PointsTransaction

    tx = PointsTransaction.objects.filter(
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        points__gt=0,
        status=PointsTransaction.Status.APPROVED,
    ).first()
    if tx:
        return revoke_points_transaction(tx, reason=reason, moderator=moderator)
    return None, False


def create_admin_adjustment(user, points, reason, moderator=None):
    """Record an authorized moderator/admin point adjustment (positive or negative)."""
    from .models import PointsTransaction

    pts = int(points)
    if pts == 0:
        return None, False
    clean_reason = (reason or "Moderator adjustment").strip()[:260]
    mod_name = getattr(moderator, "username", "staff") if moderator else "staff"
    key = f"ADMIN_ADJUSTMENT:{user.pk}:{uuid.uuid4().hex}"
    return award_points(
        user=user,
        activity_type=PointsTransaction.ActivityType.ADMIN_ADJUSTMENT,
        points=pts,
        description=f"Moderator adjustment ({mod_name}): {clean_reason}",
        related_object_type="User",
        related_object_id=user.pk,
        transaction_key=key,
        metadata={"moderator": mod_name, "reason": clean_reason},
        status=PointsTransaction.Status.APPROVED if pts > 0 else PointsTransaction.Status.REVOKED,
    )


def accept_doubt_solution(doubt_id, reply_id, acting_user):
    """Validate and process accepting a DoubtReply as the verified solution for an AcademicDoubt.
    Enforces all anti-spam and anti-abuse rules inside an atomic transaction.
    Returns (success_bool, message_str, transaction_or_None)."""
    from .models import AcademicDoubt, DoubtReply, Notification, PointsTransaction

    try:
        with transaction.atomic():
            doubt = (
                AcademicDoubt.objects.select_for_update()
                .select_related("author", "group")
                .get(pk=doubt_id)
            )
            reply = (
                DoubtReply.objects.select_for_update()
                .select_related("author")
                .get(pk=reply_id, doubt=doubt)
            )

            # 1. Authorization check: only doubt author or staff moderator
            if acting_user.pk != doubt.author_id and not getattr(acting_user, "is_staff", False):
                return False, "Only the student who asked this doubt (or a moderator) can accept a solution.", None

            # 2. One reward per academic doubt / prevent repeated acceptance
            reward_key = f"{PointsTransaction.ActivityType.DOUBT_SOLVED}:AcademicDoubt:{doubt.pk}"
            if (
                doubt.is_resolved
                or doubt.accepted_reply_id is not None
                or PointsTransaction.objects.filter(transaction_key=reward_key).exists()
            ):
                return False, "This academic doubt already has an accepted solution.", None

            # 3. No self-answer rewards
            if reply.author_id == doubt.author_id:
                return False, "You cannot accept your own reply or earn points for answering your own doubt.", None

            # 4. No rewards for flagged, empty, or meaningless responses
            if reply.is_flagged:
                return False, "Flagged replies cannot be accepted as solutions.", None

            clean_body = (reply.body or "").strip()
            distinct_words = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", clean_body)}
            if len(clean_body) < MIN_DOUBT_SOLUTION_CHARS or len(distinct_words) < MIN_DOUBT_SOLUTION_WORDS:
                return (
                    False,
                    f"Solution is too short or meaningless to qualify for a reward (at least {MIN_DOUBT_SOLUTION_CHARS} characters and {MIN_DOUBT_SOLUTION_WORDS} distinct words required).",
                    None,
                )

            # 5 & 6. Daily limits: max 5 rewarded solutions / max 100 doubt-solving points per day
            today = timezone.localdate()
            today_doubt_txs = PointsTransaction.objects.filter(
                user=reply.author,
                activity_type=PointsTransaction.ActivityType.DOUBT_SOLVED,
                created_at__date=today,
                status=PointsTransaction.Status.APPROVED,
            )
            today_count = today_doubt_txs.count()
            today_points = today_doubt_txs.aggregate(total=models.Sum("points"))["total"] or 0
            if today_count >= MAX_DAILY_DOUBT_REWARDS or (today_points + POINTS_DOUBT_SOLVED) > MAX_DAILY_DOUBT_POINTS:
                return (
                    False,
                    f"Daily limit reached: @{reply.author.username} has already earned the maximum {MAX_DAILY_DOUBT_REWARDS} doubt-solving rewards ({MAX_DAILY_DOUBT_POINTS} pts) for today.",
                    None,
                )

            # 7. Anti-collusion: detect suspicious repeated interactions between the same two students
            pair_count_today = AcademicDoubt.objects.filter(
                author=doubt.author,
                solved_by=reply.author,
                resolved_at__date=today,
                reward_revoked=False,
            ).count()
            if pair_count_today >= MAX_SAME_PAIR_DAILY_REWARDS:
                return (
                    False,
                    "Anti-abuse protection: repeated solution rewards between the same two students are limited per day.",
                    None,
                )

            # Mark reply and doubt as accepted & resolved
            now = timezone.now()
            reply.is_accepted = True
            reply.save(update_fields=["is_accepted", "updated_at"])

            doubt.is_resolved = True
            doubt.accepted_reply = reply
            doubt.solved_by = reply.author
            doubt.resolved_at = now
            doubt.reward_revoked = False
            doubt.save(update_fields=["is_resolved", "accepted_reply", "solved_by", "resolved_at", "reward_revoked", "updated_at"])

            # Create centralized ledger entry (+20 pts)
            tx, _ = award_points(
                user=reply.author,
                activity_type=PointsTransaction.ActivityType.DOUBT_SOLVED,
                points=POINTS_DOUBT_SOLVED,
                description=f"Accepted solution for “{doubt.title[:110]}” ({doubt.subject})",
                related_object_type="AcademicDoubt",
                related_object_id=doubt.pk,
                transaction_key=reward_key,
                metadata={
                    "doubt_id": doubt.pk,
                    "doubt_title": doubt.title,
                    "subject": doubt.subject,
                    "asked_by": doubt.author.username,
                    "solved_by": reply.author.username,
                    "reply_id": reply.pk,
                    "group_id": doubt.group_id,
                    "accepted_status": "Verified & Accepted",
                    "reward_date": now.strftime("%b %d, %Y %I:%M %p"),
                    "awarded_points": POINTS_DOUBT_SOLVED,
                },
            )

            Notification.objects.create(
                user=reply.author,
                text=f"Your answer to “{doubt.title[:90]}” was accepted (+{POINTS_DOUBT_SOLVED} pts!)."[:300],
                link=f"/groups/{doubt.group_id}/?tab=doubts#doubt-{doubt.pk}",
            )
            send_notification_email(
                reply.author,
                subject=f"+{POINTS_DOUBT_SOLVED} pts — Your academic solution was accepted!",
                text=f"{acting_user.username} accepted your answer on “{doubt.title}”. You earned +{POINTS_DOUBT_SOLVED} Leaderboard points.",
                link=f"/groups/{doubt.group_id}/?tab=doubts#doubt-{doubt.pk}",
            )

            return True, f"Solution accepted! @{reply.author.username} earned +{POINTS_DOUBT_SOLVED} Leaderboard points.", tx
    except AcademicDoubt.DoesNotExist:
        return False, "Academic doubt not found.", None
    except DoubtReply.DoesNotExist:
        return False, "Reply not found for this doubt.", None


def sync_user_points_ledger(user):
    """Ensure all eligible activities for the user have corresponding idempotent entries in PointsTransaction."""
    from .models import LearningProgress, MaterialReview, PointsTransaction, QuizAttempt, StudyMaterial

    if not user or not getattr(user, "pk", None):
        return

    # 1. Approved shared notes (+25)
    for mat in StudyMaterial.objects.filter(owner=user):
        if mat.is_published and not mat.is_flagged:
            award_points(
                user=user,
                activity_type=PointsTransaction.ActivityType.NOTE_SHARED,
                points=POINTS_NOTE_SHARED,
                description=f"Shared study notes: “{mat.title[:120]}” ({mat.subject})",
                related_object_type="StudyMaterial",
                related_object_id=mat.pk,
                metadata={"material_title": mat.title, "subject": mat.subject},
            )
        elif mat.is_flagged or not mat.is_published:
            revoke_points_for_object("StudyMaterial", mat.pk, reason="Resource hidden or unpublished by moderation")

    # 2. Valid resource reviews (+15)
    for rev in MaterialReview.objects.filter(author=user).select_related("material"):
        award_points(
            user=user,
            activity_type=PointsTransaction.ActivityType.RESOURCE_REVIEW,
            points=POINTS_RESOURCE_REVIEW,
            description=f"Reviewed “{rev.material.title[:120]}” ({rev.rating}/5 ★)",
            related_object_type="MaterialReview",
            related_object_id=rev.pk,
            metadata={"material_title": rev.material.title, "rating": rev.rating},
        )

    # 3. Completed study materials (+10)
    for prog in LearningProgress.objects.filter(user=user, completed=True).select_related("material"):
        award_points(
            user=user,
            activity_type=PointsTransaction.ActivityType.MATERIAL_COMPLETED,
            points=POINTS_MATERIAL_COMPLETED,
            description=f"Completed study material: “{prog.material.title[:120]}”",
            related_object_type="LearningProgress",
            related_object_id=prog.pk,
            metadata={"material_title": prog.material.title},
        )

    # 4. Completed AI quizzes (+10)
    for quiz in QuizAttempt.objects.filter(user=user):
        award_points(
            user=user,
            activity_type=PointsTransaction.ActivityType.QUIZ_COMPLETED,
            points=POINTS_QUIZ_COMPLETED,
            description=f"Completed quiz: “{(quiz.title or 'AI Practice Quiz')[:120]}” (Score: {quiz.score}%)",
            related_object_type="QuizAttempt",
            related_object_id=quiz.pk,
            metadata={"quiz_title": quiz.title or "AI Practice Quiz", "score": quiz.score},
        )


def get_user_points_summary(user):
    """Calculate a user's Total Points, Points Earned, Points Deducted, and Total Contributions
    directly from the centralized PointsTransaction ledger."""
    from .models import PointsTransaction

    sync_user_points_ledger(user)
    txs = PointsTransaction.objects.filter(user=user)
    points_earned = txs.filter(points__gt=0).aggregate(s=models.Sum("points"))["s"] or 0
    points_deducted = abs(txs.filter(points__lt=0).aggregate(s=models.Sum("points"))["s"] or 0)
    net_balance = txs.aggregate(s=models.Sum("points"))["s"] or 0
    total_contributions = txs.filter(points__gt=0, status=PointsTransaction.Status.APPROVED).count()

    return {
        "total_points": max(0, net_balance),
        "net_balance": net_balance,
        "points_earned": points_earned,
        "points_deducted": points_deducted,
        "total_contributions": total_contributions,
    }


# ---------------------------------------------------------------------------
# Default Global Group Chat & Leaderboard
# ---------------------------------------------------------------------------

GLOBAL_GC_NAME = "Global Doubt & Study Lounge"


def get_or_create_global_group(user=None):
    """Return the default platform-wide group chat, creating it if needed and
    auto-enrolling the given authenticated user so everyone can chat together.
    System welcome messages are marked is_system=True and generate 0 points."""
    from django.contrib.auth import get_user_model
    from .models import DiscussionMessage, GroupMembership, StudyGroup

    User = get_user_model()
    group = StudyGroup.objects.filter(name=GLOBAL_GC_NAME).first()
    if not group:
        owner = user if (user and getattr(user, "is_authenticated", False)) else User.objects.order_by("pk").first()
        if not owner:
            return None
        group = StudyGroup.objects.create(
            name=GLOBAL_GC_NAME,
            subject="All Subjects · Default GC",
            description="Default campus group chat where every student is connected! Use General Talk for casual conversation or switch to Academic Doubts to ask questions and earn +20 pts for accepted solutions.",
            owner=owner,
        )
        GroupMembership.objects.get_or_create(group=group, user=owner)
        DiscussionMessage.objects.create(
            group=group,
            author=owner,
            body="Welcome to the Global Doubt & Study Lounge! General Talk is for casual discussion (0 pts). Switch to the Academic Doubts tab to ask questions or provide accepted solutions (+20 pts!).",
            is_system=True,
        )

    if user and getattr(user, "is_authenticated", False):
        GroupMembership.objects.get_or_create(group=group, user=user)

    return group


def get_user_achievements(user, notes_count, accepted_solutions_count, total_points, streak_days=None):
    """Compute separate achievement badges unlocked by the student (Requirement 10)."""
    if streak_days is None:
        streak_days = get_user_streak_days(user)
    achievements = []
    if accepted_solutions_count >= 10:
        achievements.append({"name": "Problem Solver", "icon": "🏅", "desc": "10+ accepted academic solutions"})
    if notes_count >= 5:
        achievements.append({"name": "Knowledge Contributor", "icon": "📖", "desc": "5+ approved study notes shared"})
    if streak_days >= 7:
        achievements.append({"name": "Consistent Learner", "icon": "🔥", "desc": "7+ consecutive active study days"})
    if total_points >= 500:
        achievements.append({"name": "Campus Legend", "icon": "🌟", "desc": "500+ total contribution points"})
    return achievements


def get_leaderboard(limit=20):
    """Compute the community contribution leaderboard using the centralized PointsTransaction ledger:
    - Share approved study notes: +25 pts
    - Write a valid resource review: +15 pts
    - Solve an accepted academic doubt: +20 pts
    - Complete study material: +10 pts
    - Complete an AI quiz: +10 pts
    - General Talk messages: 0 pts
    """
    from django.contrib.auth import get_user_model
    from .models import (
        AcademicDoubt,
        LearningProgress,
        MaterialReview,
        QuizAttempt,
        StudyMaterial,
    )

    User = get_user_model()
    users = User.objects.select_related("profile").all()
    board = []
    for u in users:
        summary = get_user_points_summary(u)
        total_points = summary["total_points"]

        notes_count = StudyMaterial.objects.filter(owner=u, is_published=True, is_flagged=False).count()
        accepted_solutions_count = AcademicDoubt.objects.filter(
            solved_by=u, is_resolved=True, reward_revoked=False
        ).count()
        reviews_count = MaterialReview.objects.filter(author=u).count()
        completed_count = LearningProgress.objects.filter(user=u, completed=True).count()
        quiz_count = QuizAttempt.objects.filter(user=u).count()

        learning_contributions = reviews_count + completed_count + quiz_count
        streak_days = get_user_streak_days(u)

        # Primary badge calculation (exact priority preserved)
        if total_points >= 120:
            badge = "👑 Grandmaster Mentor"
            tier_class = "tier-gold"
        elif notes_count >= 2:
            badge = "📚 Top Note Sharer"
            tier_class = "tier-emerald"
        elif accepted_solutions_count >= 2:
            badge = "💡 Doubt Solver"
            tier_class = "tier-cyan"
        else:
            badge = "🚀 Active Scholar"
            tier_class = "tier-indigo"

        achievements = get_user_achievements(
            u,
            notes_count=notes_count,
            accepted_solutions_count=accepted_solutions_count,
            total_points=total_points,
            streak_days=streak_days,
        )

        board.append({
            "user": u,
            "username": u.username,
            "institution": getattr(getattr(u, "profile", None), "institution", "") or "Campus Member",
            "course": getattr(getattr(u, "profile", None), "course", "") or "General Studies",
            "avatar_url": getattr(getattr(u, "profile", None), "avatar_display_url", ""),
            "notes_count": notes_count,
            "accepted_solutions_count": accepted_solutions_count,
            "doubts_helped": accepted_solutions_count,  # template compatibility alias
            "reviews_count": reviews_count,
            "completed_count": completed_count,
            "quiz_count": quiz_count,
            "activity_count": learning_contributions,
            "learning_contributions": learning_contributions,
            "total_points": total_points,
            "points_earned": summary["points_earned"],
            "points_deducted": summary["points_deducted"],
            "total_contributions": summary["total_contributions"],
            "badge": badge,
            "tier_class": tier_class,
            "achievements": achievements,
            "streak_days": streak_days,
        })

    # Ranking priority: 1) Total points, 2) Approved notes, 3) Accepted solutions, 4) Alphabetical username
    board.sort(
        key=lambda item: (
            -item["total_points"],
            -item["notes_count"],
            -item["accepted_solutions_count"],
            item["username"].lower(),
        )
    )
    for idx, entry in enumerate(board[:limit], start=1):
        entry["rank"] = idx
    return board[:limit]


def get_user_streak_days(user):
    """Calculate the user's consecutive active study days (minimum 1 when logged in)."""
    from .models import (
        AcademicDoubt,
        DiscussionMessage,
        DoubtReply,
        LearningProgress,
        MaterialReview,
        QuizAttempt,
        StudyMaterial,
    )

    active_dates = {timezone.localdate()}
    for dt in StudyMaterial.objects.filter(owner=user).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in DiscussionMessage.objects.filter(author=user, is_system=False).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in AcademicDoubt.objects.filter(author=user).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in DoubtReply.objects.filter(author=user).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in LearningProgress.objects.filter(user=user).values_list("last_opened_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in MaterialReview.objects.filter(author=user).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))
    for dt in QuizAttempt.objects.filter(user=user).values_list("created_at", flat=True):
        active_dates.add(timezone.localdate(dt))

    streak = 0
    cursor = timezone.localdate()
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return max(streak, 1)
