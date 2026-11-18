from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import (
    AcademicDoubt,
    ContentReport,
    DiscussionMessage,
    DoubtReply,
    MaterialReview,
    Profile,
    StudyCollection,
    StudyGroup,
    StudyMaterial,
)


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")


class MaterialForm(forms.ModelForm):
    class Meta:
        model = StudyMaterial
        fields = ("title", "description", "subject", "topic", "material_type", "file", "external_link")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "file": forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg,.webp,.txt,.md,.doc,.docx,.ppt,.pptx"}),
        }
        help_texts = {
            "file": "Supported formats: PDF, PNG, JPG, WebP, TXT, MD, Word (.doc/.docx), PowerPoint (.ppt/.pptx) — up to 15 MB.",
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("file") and not cleaned.get("external_link"):
            raise forms.ValidationError("Add a file or a link so classmates can access this resource.")
        return cleaned

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file
        allowed = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md", ".doc", ".docx", ".ppt", ".pptx"}
        suffix = "." + file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        if suffix not in allowed:
            raise forms.ValidationError("Upload a PDF, PNG/image, text, Word, or PowerPoint file.")
        if file.size > 15 * 1024 * 1024:
            raise forms.ValidationError("Files must be 15 MB or smaller.")
        return file


class ReviewForm(forms.ModelForm):
    class Meta:
        model = MaterialReview
        fields = ("rating", "comment")
        widgets = {"comment": forms.Textarea(attrs={"rows": 3, "placeholder": "What made this resource useful?"})}


class GroupForm(forms.ModelForm):
    class Meta:
        model = StudyGroup
        fields = ("name", "subject", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class MessageForm(forms.ModelForm):
    class Meta:
        model = DiscussionMessage
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Ask a question or share an idea…"})}


class ReportForm(forms.ModelForm):
    class Meta:
        model = ContentReport
        fields = ("reason", "details")
        widgets = {"details": forms.Textarea(attrs={"rows": 3})}


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("institution", "course", "bio", "avatar", "avatar_url", "study_goal", "email_notifications")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}
        labels = {
            "avatar": "Upload avatar image",
            "avatar_url": "Or paste an avatar URL",
            "email_notifications": "Receive email notifications",
        }
        help_texts = {
            "avatar": "Upload a JPG, PNG, or WebP image (max 2 MB).",
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if not avatar:
            return avatar
        allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        suffix = "." + avatar.name.rsplit(".", 1)[-1].lower() if "." in avatar.name else ""
        if suffix not in allowed:
            raise forms.ValidationError("Upload a JPG, PNG, WebP, or GIF image.")
        if avatar.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Avatar images must be 2 MB or smaller.")
        return avatar


class CollectionForm(forms.ModelForm):
    class Meta:
        model = StudyCollection
        fields = ("name", "description")


class AcademicDoubtForm(forms.ModelForm):
    class Meta:
        model = AcademicDoubt
        fields = ("title", "subject", "tagged_username", "body")
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. How does Bellman-Ford detect negative weight cycles?"}),
            "subject": forms.TextInput(attrs={"placeholder": "e.g. Computer Science, Calculus, Physics"}),
            "tagged_username": forms.TextInput(attrs={"placeholder": "Optional: @username to tag a classmate"}),
            "body": forms.Textarea(attrs={"rows": 4, "placeholder": "Describe your academic doubt clearly so peers can explain it step by step…"}),
        }
        labels = {
            "title": "Doubt Title",
            "subject": "Subject / Category",
            "tagged_username": "Tag a Student (Optional)",
            "body": "Detailed Doubt Description",
        }

    def clean_tagged_username(self):
        val = (self.cleaned_data.get("tagged_username") or "").strip().lstrip("@")
        return val


class DoubtReplyForm(forms.ModelForm):
    class Meta:
        model = DoubtReply
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write a clear academic explanation (minimum 15 characters & 3 words to qualify for +20 pts if accepted)…",
                }
            ),
        }
        labels = {"body": "Your Explanation / Reply"}

