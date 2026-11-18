# Generated manually for the initial StudySphere domain models.
from django.conf import settings
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("institution", models.CharField(blank=True, max_length=160)),
                ("course", models.CharField(blank=True, max_length=160)),
                ("bio", models.TextField(blank=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="StudyGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField()),
                ("subject", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owned_groups", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StudyMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=220)),
                ("description", models.TextField()),
                ("subject", models.CharField(max_length=120)),
                ("topic", models.CharField(blank=True, max_length=160)),
                ("material_type", models.CharField(choices=[("note", "Notes"), ("pdf", "PDF"), ("assignment", "Assignment"), ("question_paper", "Question paper"), ("other", "Other")], default="note", max_length=20)),
                ("file", models.FileField(blank=True, upload_to="materials/%Y/%m/")),
                ("external_link", models.URLField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("downloads", models.PositiveIntegerField(default=0)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materials", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="LearningProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completed", models.BooleanField(default=False)),
                ("last_opened_at", models.DateTimeField(auto_now=True)),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="hub.studymaterial")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progress_entries", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="GroupMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="hub.studygroup")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="DiscussionMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="hub.studygroup")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="MaterialReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="hub.studymaterial")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ContentReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=300)),
                ("details", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved", models.BooleanField(default=False)),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="hub.studymaterial")),
                ("reporter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="studygroup",
            name="members",
            field=models.ManyToManyField(related_name="study_groups", through="hub.GroupMembership", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(model_name="learningprogress", constraint=models.UniqueConstraint(fields=("user", "material"), name="unique_material_progress")),
        migrations.AddConstraint(model_name="groupmembership", constraint=models.UniqueConstraint(fields=("group", "user"), name="unique_group_member")),
        migrations.AddConstraint(model_name="materialreview", constraint=models.UniqueConstraint(fields=("material", "author"), name="unique_material_reviewer")),
    ]
