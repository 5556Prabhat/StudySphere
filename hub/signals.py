from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    LearningProgress,
    MaterialReview,
    PointsTransaction,
    Profile,
    QuizAttempt,
    StudyMaterial,
)
from .services import (
    POINTS_MATERIAL_COMPLETED,
    POINTS_NOTE_SHARED,
    POINTS_QUIZ_COMPLETED,
    POINTS_RESOURCE_REVIEW,
    award_points,
    revoke_points_for_object,
)


@receiver(post_save, sender=get_user_model())
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=StudyMaterial)
def sync_study_material_points(sender, instance, **kwargs):
    if instance.is_published and not instance.is_flagged:
        award_points(
            user=instance.owner,
            activity_type=PointsTransaction.ActivityType.NOTE_SHARED,
            points=POINTS_NOTE_SHARED,
            description=f"Shared study notes: “{instance.title[:120]}” ({instance.subject})",
            related_object_type="StudyMaterial",
            related_object_id=instance.pk,
            metadata={"material_title": instance.title, "subject": instance.subject},
        )
    else:
        revoke_points_for_object(
            "StudyMaterial",
            instance.pk,
            reason="Resource hidden or unpublished after moderation",
        )


@receiver(post_delete, sender=StudyMaterial)
def revoke_deleted_material_points(sender, instance, **kwargs):
    revoke_points_for_object(
        "StudyMaterial",
        instance.pk,
        reason="Study material deleted by owner",
    )


@receiver(post_save, sender=MaterialReview)
def sync_material_review_points(sender, instance, **kwargs):
    award_points(
        user=instance.author,
        activity_type=PointsTransaction.ActivityType.RESOURCE_REVIEW,
        points=POINTS_RESOURCE_REVIEW,
        description=f"Reviewed “{instance.material.title[:120]}” ({instance.rating}/5 ★)",
        related_object_type="MaterialReview",
        related_object_id=instance.pk,
        metadata={"material_title": instance.material.title, "rating": instance.rating},
    )


@receiver(post_save, sender=LearningProgress)
def sync_learning_progress_points(sender, instance, **kwargs):
    if instance.completed:
        award_points(
            user=instance.user,
            activity_type=PointsTransaction.ActivityType.MATERIAL_COMPLETED,
            points=POINTS_MATERIAL_COMPLETED,
            description=f"Completed study material: “{instance.material.title[:120]}”",
            related_object_type="LearningProgress",
            related_object_id=instance.pk,
            metadata={"material_title": instance.material.title},
        )
    else:
        revoke_points_for_object(
            "LearningProgress",
            instance.pk,
            reason="Study material marked incomplete",
        )


@receiver(post_save, sender=QuizAttempt)
def sync_quiz_attempt_points(sender, instance, **kwargs):
    award_points(
        user=instance.user,
        activity_type=PointsTransaction.ActivityType.QUIZ_COMPLETED,
        points=POINTS_QUIZ_COMPLETED,
        description=f"Completed quiz: “{(instance.title or 'AI Practice Quiz')[:120]}” (Score: {instance.score}%)",
        related_object_type="QuizAttempt",
        related_object_id=instance.pk,
        metadata={"quiz_title": instance.title or "AI Practice Quiz", "score": instance.score},
    )
