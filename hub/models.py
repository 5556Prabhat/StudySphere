from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    institution = models.CharField(max_length=160, blank=True)
    course = models.CharField(max_length=160, blank=True)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)
    avatar = models.ImageField(upload_to="avatars/%Y/", blank=True)
    study_goal = models.CharField(max_length=240, blank=True)
    email_notifications = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_username()

    @property
    def avatar_display_url(self):
        """Return the uploaded avatar URL, falling back to avatar_url field."""
        if self.avatar:
            return self.avatar.url
        return self.avatar_url or ""


class StudyMaterial(models.Model):
    class MaterialType(models.TextChoices):
        NOTE = "note", "Notes"
        PDF = "pdf", "PDF"
        PNG = "png", "PNG / Image"
        ASSIGNMENT = "assignment", "Assignment"
        QUESTION_PAPER = "question_paper", "Question paper"
        OTHER = "other", "Other"

    title = models.CharField(max_length=220)
    description = models.TextField()
    subject = models.CharField(max_length=120)
    topic = models.CharField(max_length=160, blank=True)
    material_type = models.CharField(max_length=20, choices=MaterialType.choices, default=MaterialType.NOTE)
    file = models.FileField(upload_to="materials/%Y/%m/", blank=True)
    external_link = models.URLField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="materials")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    downloads = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    is_flagged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("material_detail", args=[self.pk])

    @property
    def average_rating(self):
        return self.reviews.aggregate(models.Avg("rating"))["rating__avg"] or 0

    @property
    def is_image_file(self):
        return bool(self.file and self.file.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")))


class MaterialReview(models.Model):
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="reviews")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["material", "author"], name="unique_material_reviewer")]
        ordering = ["-created_at"]


class StudyGroup(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField()
    subject = models.CharField(max_length=120)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_groups")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="GroupMembership", related_name="study_groups")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="unique_group_member")]


class DiscussionMessage(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField(max_length=2000)
    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class AcademicDoubt(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="doubts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asked_doubts")
    title = models.CharField(max_length=220)
    body = models.TextField(max_length=4000)
    subject = models.CharField(max_length=120, default="General")
    tagged_username = models.CharField(max_length=150, blank=True)
    is_resolved = models.BooleanField(default=False)
    accepted_reply = models.OneToOneField(
        "DoubtReply",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_for_doubt",
    )
    solved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solved_doubts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    reward_revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class DoubtReply(models.Model):
    doubt = models.ForeignKey(AcademicDoubt, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doubt_replies")
    body = models.TextField(max_length=3000)
    is_accepted = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Reply by {self.author.username} on #{self.doubt_id}"


class LearningProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress_entries")
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    last_opened_at = models.DateTimeField(auto_now=True)
    review_due_at = models.DateTimeField(null=True, blank=True)
    review_interval_days = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "material"], name="unique_material_progress")]

    def complete_and_schedule(self):
        self.completed = True
        self.review_due_at = timezone.now() + timedelta(days=self.review_interval_days)
        self.review_interval_days = min(self.review_interval_days * 2, 60)
        self.save(update_fields=["completed", "review_due_at", "review_interval_days", "last_opened_at"])


class ContentReport(models.Model):
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reason = models.CharField(max_length=300)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    text = models.CharField(max_length=300)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class StudyCollection(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_user_collection_name")]
        ordering = ["name"]


class SavedMaterial(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_materials")
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name="saved_by")
    collection = models.ForeignKey(StudyCollection, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "material"], name="unique_saved_material")]
        ordering = ["-saved_at"]


class AIUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_usage")
    action = models.CharField(max_length=30)
    provider = models.CharField(max_length=30)
    input_characters = models.PositiveIntegerField()
    output_characters = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    title = models.CharField(max_length=180, blank=True)
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PointsTransaction(models.Model):
    class ActivityType(models.TextChoices):
        NOTE_SHARED = "NOTE_SHARED", "Study Notes Shared"
        RESOURCE_REVIEW = "RESOURCE_REVIEW", "Resource Review Submitted"
        DOUBT_SOLVED = "DOUBT_SOLVED", "Academic Doubt Solved"
        MATERIAL_COMPLETED = "MATERIAL_COMPLETED", "Study Material Completed"
        QUIZ_COMPLETED = "QUIZ_COMPLETED", "AI Quiz Completed"
        REWARD_REVOKED = "REWARD_REVOKED", "Reward Revoked"
        ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT", "Moderator Adjustment"

    class Status(models.TextChoices):
        APPROVED = "approved", "Approved"
        PENDING = "pending", "Pending"
        REVOKED = "revoked", "Revoked"

    transaction_key = models.CharField(max_length=150, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_transactions")
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    description = models.CharField(max_length=300)
    points = models.IntegerField()
    related_object_type = models.CharField(max_length=60, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.APPROVED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "activity_type"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        sign = "+" if self.points > 0 else ""
        return f"{self.user.username}: {self.activity_type} ({sign}{self.points} pts)"

