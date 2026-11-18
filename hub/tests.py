from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import (AIUsage, ContentReport, GroupMembership, LearningProgress,
                     Notification, SavedMaterial, StudyGroup, StudyMaterial)
from .services import extract_text_from_upload, grade_quiz, parse_quiz_result


class StudySphereTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="strong-pass-123")
        self.learner = User.objects.create_user("learner", password="strong-pass-123")
        self.staff = User.objects.create_user("staff", password="strong-pass-123", is_staff=True)
        self.material = StudyMaterial.objects.create(
            title="Calculus limits", description="A clear introduction to limits.", subject="Mathematics",
            external_link="https://example.com/limits", owner=self.owner,
        )

    def test_new_user_gets_profile(self):
        self.assertEqual(self.owner.profile.user, self.owner)

    def test_hidden_material_is_not_listed(self):
        self.material.is_flagged = True
        self.material.save()
        response = self.client.get(reverse("material_list"))
        self.assertNotContains(response, self.material.title)

    def test_save_material_toggles(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.post(reverse("toggle_saved", args=[self.material.pk]))
        self.assertTrue(SavedMaterial.objects.filter(user=self.learner, material=self.material).exists())
        self.client.post(reverse("toggle_saved", args=[self.material.pk]))
        self.assertFalse(SavedMaterial.objects.filter(user=self.learner, material=self.material).exists())

    def test_review_notifies_owner(self):
        self.client.login(username="learner", password="strong-pass-123")
        response = self.client.post(reverse("review_material", args=[self.material.pk]), {"rating": 5, "comment": "Very useful"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(user=self.owner, text__contains="reviewed").exists())

    def test_completion_schedules_review(self):
        self.client.login(username="learner", password="strong-pass-123")
        self.client.post(reverse("toggle_progress", args=[self.material.pk]))
        progress = LearningProgress.objects.get(user=self.learner, material=self.material)
        self.assertTrue(progress.completed)
        self.assertGreater(progress.review_due_at, timezone.now())

    def test_non_member_cannot_post_to_group(self):
        group = StudyGroup.objects.create(name="Math group", subject="Mathematics", description="Study together", owner=self.owner)
        GroupMembership.objects.create(group=group, user=self.owner)
        self.client.login(username="learner", password="strong-pass-123")
        response = self.client.post(reverse("post_message", args=[group.pk]), {"body": "Hello"})
        self.assertEqual(response.status_code, 403)

    def test_staff_can_hide_reported_material(self):
        report = ContentReport.objects.create(material=self.material, reporter=self.learner, reason="Incorrect")
        self.client.login(username="staff", password="strong-pass-123")
        response = self.client.post(reverse("resolve_report", args=[report.pk]), {"hide": "1"})
        self.assertEqual(response.status_code, 302)
        self.material.refresh_from_db()
        self.assertTrue(self.material.is_flagged)

    def test_ai_studio_records_usage_with_local_fallback(self):
        self.client.login(username="learner", password="strong-pass-123")
        response = self.client.post(reverse("ai_studio"), {"source": "Limits describe what a function approaches.", "action": "summary"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AIUsage.objects.filter(user=self.learner).count(), 1)


class EmailNotificationTests(TestCase):
    """Test that email notifications are sent when events happen."""

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_review_sends_email(self):
        owner = User.objects.create_user("owner2", email="owner@example.com", password="strong-pass-123")
        learner = User.objects.create_user("learner2", password="strong-pass-123")
        material = StudyMaterial.objects.create(
            title="Physics 101", description="Mechanics.", subject="Physics",
            external_link="https://example.com/phys", owner=owner,
        )
        self.client.login(username="learner2", password="strong-pass-123")
        self.client.post(reverse("review_material", args=[material.pk]), {"rating": 4, "comment": "Great"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("StudySphere", mail.outbox[0].subject)
        self.assertIn("owner@example.com", mail.outbox[0].to)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_opt_out_disables_emails(self):
        owner = User.objects.create_user("owner3", email="owner3@example.com", password="strong-pass-123")
        owner.profile.email_notifications = False
        owner.profile.save()
        learner = User.objects.create_user("learner3", password="strong-pass-123")
        material = StudyMaterial.objects.create(
            title="Biology 101", description="Cells.", subject="Biology",
            external_link="https://example.com/bio", owner=owner,
        )
        self.client.login(username="learner3", password="strong-pass-123")
        self.client.post(reverse("review_material", args=[material.pk]), {"rating": 3, "comment": "OK"})
        self.assertEqual(len(mail.outbox), 0)


class QuizAutoGradingTests(TestCase):
    """Test the quiz auto-grading logic."""

    def test_grade_quiz_perfect_score(self):
        quiz_data = [
            {"question": "Q1", "choices": ["A) Yes", "B) No", "C) Maybe", "D) None"], "answer": "A", "explanation": "Yes."},
            {"question": "Q2", "choices": ["A) X", "B) Y", "C) Z", "D) W"], "answer": "B", "explanation": "Y."},
        ]
        user_answers = {"0": "A", "1": "B"}
        score, total, correct, results = grade_quiz(quiz_data, user_answers)
        self.assertEqual(score, 100)
        self.assertEqual(total, 2)
        self.assertEqual(correct, 2)
        self.assertTrue(all(r["is_correct"] for r in results))

    def test_grade_quiz_partial(self):
        quiz_data = [
            {"question": "Q1", "choices": ["A) a", "B) b", "C) c", "D) d"], "answer": "A", "explanation": ""},
            {"question": "Q2", "choices": ["A) a", "B) b", "C) c", "D) d"], "answer": "C", "explanation": ""},
        ]
        user_answers = {"0": "A", "1": "B"}
        score, total, correct, results = grade_quiz(quiz_data, user_answers)
        self.assertEqual(score, 50)
        self.assertEqual(correct, 1)
        self.assertTrue(results[0]["is_correct"])
        self.assertFalse(results[1]["is_correct"])

    def test_parse_quiz_result_valid_json(self):
        import json
        data = [{"question": "Q", "choices": ["A) a"], "answer": "A", "explanation": ""}]
        result = parse_quiz_result(json.dumps(data))
        self.assertEqual(len(result), 1)

    def test_parse_quiz_result_invalid(self):
        result = parse_quiz_result("not json at all")
        self.assertEqual(result, [])

    def test_local_quiz_generates_json(self):
        from .services import local_learning_assist
        result = local_learning_assist("The quick brown fox jumps over the lazy dog. Mitosis is cell division. Photosynthesis converts light.", "quiz")
        parsed = parse_quiz_result(result)
        self.assertIsInstance(parsed, list)
        self.assertGreater(len(parsed), 0)


class AvatarTests(TestCase):
    """Test avatar field on profile."""

    def test_profile_has_avatar_display_url(self):
        user = User.objects.create_user("avatar_user", password="strong-pass-123")
        self.assertEqual(user.profile.avatar_display_url, "")

    def test_profile_avatar_url_fallback(self):
        user = User.objects.create_user("avatar_user2", password="strong-pass-123")
        user.profile.avatar_url = "https://example.com/pic.jpg"
        user.profile.save()
        self.assertEqual(user.profile.avatar_display_url, "https://example.com/pic.jpg")


class HealthCheckTests(TestCase):
    """Test the health-check endpoint."""

    def test_health_check_returns_ok(self):
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["database"])


class MiddlewareTests(TestCase):
    """Test the error logging middleware is wired correctly."""

    def test_404_still_works(self):
        response = self.client.get("/nonexistent-url-12345/")
        self.assertEqual(response.status_code, 404)


class DocumentExtractionTests(TestCase):
    """Test DOCX and PPTX text extraction."""

    def test_docx_extraction(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from docx import Document

        doc = Document()
        doc.add_paragraph("Thermodynamics first law states energy is conserved.")
        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)
        upload = SimpleUploadedFile("notes.docx", buf.read())
        extracted = extract_text_from_upload(upload)
        self.assertIn("Thermodynamics first law", extracted)

    def test_pptx_extraction(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from pptx import Presentation

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        slide.shapes.title.text = "Linear Algebra Eigenvalues"
        buf = BytesIO()
        prs.save(buf)
        buf.seek(0)
        upload = SimpleUploadedFile("slides.pptx", buf.read())
        extracted = extract_text_from_upload(upload)
        self.assertIn("Linear Algebra Eigenvalues", extracted)

    def test_upload_pdf_and_png_via_material_create_view(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        user = User.objects.create_user("uploader", password="strong-pass-123")
        self.client.login(username="uploader", password="strong-pass-123")
        png_file = SimpleUploadedFile("diagram.png", b"\x89PNG\r\n\x1a\nfake", content_type="image/png")
        resp = self.client.post(
            reverse("material_create"),
            {
                "title": "Handwritten Circuit Diagram",
                "description": "PNG diagram for RLC circuits.",
                "subject": "Electronics",
                "topic": "RLC",
                "material_type": "png",
                "file": png_file,
            },
        )
        self.assertEqual(resp.status_code, 302)
        created = StudyMaterial.objects.get(title="Handwritten Circuit Diagram")
        self.assertTrue(created.is_image_file)


class QuizGradeViewTests(TestCase):
    """Test end-to-end quiz generation and auto-grading HTTP view."""

    def test_generate_and_grade_quiz_flow(self):
        user = User.objects.create_user("quizzer", password="strong-pass-123")
        self.client.login(username="quizzer", password="strong-pass-123")
        self.client.post(
            reverse("ai_studio"),
            {
                "source": "Photosynthesis converts light energy into chemical energy. Cellular respiration releases ATP.",
                "action": "quiz",
            },
        )
        response = self.client.post(reverse("grade_quiz"), {"answer_0": "A", "answer_1": "A"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100%")
        self.assertEqual(user.quiz_attempts.count(), 1)
        self.assertEqual(user.quiz_attempts.first().score, 100)


class DashboardAndLeaderboardTests(TestCase):
    """Test the redesigned Dashboard Hub, Default Global Group Chat, and Leaderboard."""

    def setUp(self):
        self.u1 = User.objects.create_user("contributor1", password="strong-pass-123")
        self.u2 = User.objects.create_user("contributor2", password="strong-pass-123")
        StudyMaterial.objects.create(
            title="Operating Systems Deadlocks",
            description="Banker's algorithm and resource allocation graphs.",
            subject="Computer Science",
            external_link="https://example.com/os",
            owner=self.u1,
        )

    def test_dashboard_shows_all_four_hub_sections(self):
        self.client.login(username="contributor2", password="strong-pass-123")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share Notes")
        self.assertContains(response, "Shared Notes by Other Users")
        self.assertContains(response, "Global Doubt &amp; Study Lounge")
        self.assertContains(response, "Contribution Leaderboard")
        self.assertContains(response, "Operating Systems Deadlocks")

    def test_default_global_gc_allows_any_user_to_post(self):
        self.client.login(username="contributor2", password="strong-pass-123")
        response = self.client.get(reverse("global_chat"))
        self.assertEqual(response.status_code, 200)
        group = response.context["group"]
        post_resp = self.client.post(
            reverse("post_message", args=[group.pk]),
            {"body": "Can someone explain mutex vs semaphore?", "next": "dashboard"},
        )
        self.assertEqual(post_resp.status_code, 302)
        self.assertTrue(group.messages.filter(author=self.u2, body__contains="mutex").exists())

    def test_leaderboard_ranks_by_contribution_points(self):
        from .services import get_leaderboard, get_or_create_global_group

        gc = get_or_create_global_group(self.u1)
        # u1 shared 1 note (25 pts) + 1 welcome message in GC (10 pts) = 35 pts
        board = get_leaderboard()
        self.assertEqual(board[0]["username"], "contributor1")
        self.assertGreaterEqual(board[0]["total_points"], 25)
        resp = self.client.get(reverse("leaderboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Campus Leaderboard")
        self.assertContains(resp, "@contributor1")


class PasswordResetOTPTests(TestCase):
    """Test the 3-step Email OTP forgot-password and reset flow."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="otpuser",
            email="otpuser@example.com",
            password="old-password-123",
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_forgot_password_email_otp_and_reset_flow(self):
        # Step 1: Request OTP
        resp1 = self.client.post(reverse("forgot_password"), {"identifier": "otpuser@example.com"})
        self.assertRedirects(resp1, reverse("verify_reset_otp"))
        self.assertEqual(len(mail.outbox), 1)

        otp_data = self.client.session.get("password_reset_otp")
        self.assertIsNotNone(otp_data)
        otp_code = otp_data["otp"]
        self.assertIn(otp_code, mail.outbox[0].subject)

        # Step 2: Verify OTP
        resp2 = self.client.post(reverse("verify_reset_otp"), {"otp": otp_code})
        self.assertRedirects(resp2, reverse("reset_password_new"))

        # Step 3: Set new password
        resp3 = self.client.post(
            reverse("reset_password_new"),
            {"password1": "new-secure-pass-999", "password2": "new-secure-pass-999"},
        )
        self.assertRedirects(resp3, reverse("login"))

        # Confirm login works with the new password
        self.assertTrue(self.client.login(username="otpuser", password="new-secure-pass-999"))


class AcademicDoubtAndPointsLedgerTests(TestCase):
    """Comprehensive tests for General Talk (0 pts), Academic Doubts (+20 pts),
    anti-spam/anti-abuse rules, PointsTransaction ledger, revocation, and Points History."""

    def setUp(self):
        from .services import get_or_create_global_group

        self.asker = User.objects.create_user("asker", password="strong-pass-123")
        self.solver = User.objects.create_user("solver", password="strong-pass-123")
        self.other = User.objects.create_user("other_student", password="strong-pass-123")
        self.moderator = User.objects.create_user("mod", password="strong-pass-123", is_staff=True)
        self.group = get_or_create_global_group(self.asker)
        GroupMembership.objects.get_or_create(group=self.group, user=self.solver)
        GroupMembership.objects.get_or_create(group=self.group, user=self.other)

    def test_100_general_talk_messages_produce_zero_points(self):
        from .models import DiscussionMessage
        from .services import get_user_points_summary

        DiscussionMessage.objects.bulk_create([
            DiscussionMessage(group=self.group, author=self.solver, body=f"Casual chat message {i}")
            for i in range(100)
        ])
        summary = get_user_points_summary(self.solver)
        self.assertEqual(summary["total_points"], 0)
        self.assertEqual(summary["points_earned"], 0)

    def test_creating_doubt_and_ordinary_reply_produce_zero_points(self):
        from .models import AcademicDoubt, DoubtReply
        from .services import get_user_points_summary

        self.client.login(username="asker", password="strong-pass-123")
        self.client.post(
            reverse("create_doubt", args=[self.group.pk]),
            {
                "title": "Why does Dijkstra fail on negative edge weights?",
                "subject": "Algorithms",
                "tagged_username": "@solver",
                "body": "Please explain with an example graph.",
            },
        )
        doubt = AcademicDoubt.objects.get(author=self.asker)
        self.assertEqual(get_user_points_summary(self.asker)["total_points"], 0)

        self.client.login(username="solver", password="strong-pass-123")
        self.client.post(
            reverse("reply_doubt", args=[doubt.pk]),
            {"body": "Because Dijkstra greedily locks vertices assuming paths only grow longer."},
        )
        self.assertEqual(DoubtReply.objects.filter(doubt=doubt).count(), 1)
        # Ordinary unaccepted reply awards 0 points
        self.assertEqual(get_user_points_summary(self.solver)["total_points"], 0)

    def test_accepting_valid_solution_awards_20_points_and_updates_leaderboard(self):
        from .models import AcademicDoubt, DoubtReply
        from .services import get_leaderboard, get_user_points_summary

        doubt = AcademicDoubt.objects.create(
            group=self.group,
            author=self.asker,
            title="Time complexity of Merge Sort",
            subject="Computer Science",
            body="Why is Merge Sort O(n log n) in all cases?",
        )
        reply = DoubtReply.objects.create(
            doubt=doubt,
            author=self.solver,
            body="Merge sort divides the array into halves in log n levels and merges n elements per level.",
        )

        self.client.login(username="asker", password="strong-pass-123")
        resp = self.client.post(reverse("accept_doubt_reply", args=[doubt.pk, reply.pk]))
        self.assertEqual(resp.status_code, 302)

        doubt.refresh_from_db()
        reply.refresh_from_db()
        self.assertTrue(doubt.is_resolved)
        self.assertTrue(reply.is_accepted)
        self.assertEqual(doubt.solved_by, self.solver)

        solver_summary = get_user_points_summary(self.solver)
        self.assertEqual(solver_summary["total_points"], 20)
        self.assertEqual(get_user_points_summary(self.asker)["total_points"], 0)

        board = get_leaderboard()
        self.assertEqual(board[0]["username"], "solver")
        self.assertEqual(board[0]["accepted_solutions_count"], 1)
        self.assertEqual(board[0]["total_points"], 20)

    def test_anti_spam_no_self_answer_no_double_accept_no_short_reply(self):
        from .models import AcademicDoubt, DoubtReply
        from .services import accept_doubt_solution, get_user_points_summary

        doubt = AcademicDoubt.objects.create(
            group=self.group,
            author=self.asker,
            title="Self answer & short answer test",
            subject="Math",
            body="Testing anti-abuse validations.",
        )
        # 1. Self-answer attempt
        self_reply = DoubtReply.objects.create(
            doubt=doubt,
            author=self.asker,
            body="Here is my own detailed explanation with many words.",
        )
        ok, msg, _ = accept_doubt_solution(doubt.pk, self_reply.pk, self.asker)
        self.assertFalse(ok)
        self.assertEqual(get_user_points_summary(self.asker)["total_points"], 0)

        # 2. Meaningless/short reply attempt
        short_reply = DoubtReply.objects.create(doubt=doubt, author=self.solver, body="yes ok")
        ok, msg, _ = accept_doubt_solution(doubt.pk, short_reply.pk, self.asker)
        self.assertFalse(ok)
        self.assertEqual(get_user_points_summary(self.solver)["total_points"], 0)

        # 3. Valid reply accepted once, then second acceptance attempt on same doubt rejected
        valid_reply = DoubtReply.objects.create(
            doubt=doubt,
            author=self.solver,
            body="A complete, meaningful explanation of the mathematical theorem and proof.",
        )
        other_reply = DoubtReply.objects.create(
            doubt=doubt,
            author=self.other,
            body="Another valid explanation posted by a second classmate for testing.",
        )
        ok1, _, _ = accept_doubt_solution(doubt.pk, valid_reply.pk, self.asker)
        self.assertTrue(ok1)
        ok2, _, _ = accept_doubt_solution(doubt.pk, valid_reply.pk, self.asker)
        self.assertFalse(ok2)
        ok3, _, _ = accept_doubt_solution(doubt.pk, other_reply.pk, self.asker)
        self.assertFalse(ok3)
        self.assertEqual(get_user_points_summary(self.solver)["total_points"], 20)
        self.assertEqual(get_user_points_summary(self.other)["total_points"], 0)

    def test_daily_reward_limit_enforced(self):
        from .models import AcademicDoubt, DoubtReply
        from .services import accept_doubt_solution, get_user_points_summary

        # Create 6 different askers so pair-limit doesn't trigger before daily limit (5)
        for i in range(6):
            asker_i = User.objects.create_user(f"asker_{i}", password="strong-pass-123")
            d = AcademicDoubt.objects.create(
                group=self.group,
                author=asker_i,
                title=f"Doubt number {i}",
                subject="Physics",
                body="Explain conservation of momentum in elastic collisions.",
            )
            r = DoubtReply.objects.create(
                doubt=d,
                author=self.solver,
                body=f"Detailed physics explanation number {i} covering momentum and kinetic energy.",
            )
            ok, msg, _ = accept_doubt_solution(d.pk, r.pk, asker_i)
            if i < 5:
                self.assertTrue(ok, msg)
            else:
                # 6th solution on the same day must be blocked (max 5 / 100 pts per day)
                self.assertFalse(ok)
                self.assertIn("Daily limit reached", msg)

        self.assertEqual(get_user_points_summary(self.solver)["total_points"], 100)

    def test_revoke_reward_keeps_history_and_updates_balance(self):
        from .models import AcademicDoubt, DoubtReply, PointsTransaction
        from .services import accept_doubt_solution, get_user_points_summary

        doubt = AcademicDoubt.objects.create(
            group=self.group,
            author=self.asker,
            title="Revocation test doubt",
            subject="Chemistry",
            body="How do covalent bonds form?",
        )
        reply = DoubtReply.objects.create(
            doubt=doubt,
            author=self.solver,
            body="Atoms share electron pairs to achieve a stable outer shell configuration.",
        )
        accept_doubt_solution(doubt.pk, reply.pk, self.asker)
        self.assertEqual(get_user_points_summary(self.solver)["total_points"], 20)

        # Moderator revokes the reward
        self.client.login(username="mod", password="strong-pass-123")
        resp = self.client.post(
            reverse("revoke_doubt_reward", args=[doubt.pk]),
            {"reason": "Plagiarized answer flagged by moderation"},
        )
        self.assertEqual(resp.status_code, 302)

        summary = get_user_points_summary(self.solver)
        self.assertEqual(summary["points_earned"], 20)
        self.assertEqual(summary["points_deducted"], 20)
        self.assertEqual(summary["total_points"], 0)

        # Both original (+20) and reversal (-20) remain visible in PointsTransaction
        txs = PointsTransaction.objects.filter(user=self.solver)
        self.assertEqual(txs.count(), 2)
        self.assertTrue(txs.filter(points=20, status="revoked").exists())
        self.assertTrue(txs.filter(points=-20, activity_type="REWARD_REVOKED").exists())

    def test_points_history_view_filters_and_privacy_authorization(self):
        from .models import QuizAttempt

        StudyMaterial.objects.create(
            title="Linear Algebra Notes",
            description="Vector spaces and linear maps.",
            subject="Mathematics",
            external_link="https://example.com/la",
            owner=self.solver,
        )
        QuizAttempt.objects.create(user=self.solver, title="Matrix Quiz", score=90)

        # Solver can view their own history and filter by activity_type
        self.client.login(username="solver", password="strong-pass-123")
        resp = self.client.get(reverse("points_history"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Linear Algebra Notes")
        self.assertContains(resp, "Matrix Quiz")
        self.assertContains(resp, "+35")

        filtered = self.client.get(reverse("points_history"), {"activity_type": "QUIZ_COMPLETED"})
        self.assertContains(filtered, "Matrix Quiz")
        self.assertNotContains(filtered, "Linear Algebra Notes")

        # Another non-staff student cannot access solver's private transaction history
        self.client.login(username="other_student", password="strong-pass-123")
        forbidden_resp = self.client.get(reverse("points_history"), {"user_id": self.solver.pk})
        self.assertEqual(forbidden_resp.status_code, 403)
        # Non-staff student cannot call staff revoke endpoint
        tx = self.solver.point_transactions.first()
        forbidden_revoke = self.client.post(reverse("revoke_transaction", args=[tx.pk]), {"reason": "hack"})
        self.assertEqual(forbidden_revoke.status_code, 403)




