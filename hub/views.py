import json
import logging
import re

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import (
    AcademicDoubtForm,
    CollectionForm,
    DoubtReplyForm,
    GroupForm,
    MaterialForm,
    MessageForm,
    ProfileForm,
    ReportForm,
    ReviewForm,
    SignUpForm,
)
from .models import (
    AIUsage,
    AcademicDoubt,
    ContentReport,
    DiscussionMessage,
    DoubtReply,
    GroupAccessRequest,
    GroupMembership,
    LearningProgress,
    MaterialReview,
    Notification,
    PointsTransaction,
    Profile,
    QuizAttempt,
    SavedMaterial,
    StudyCollection,
    StudyGroup,
    StudyMaterial,
)
from .services import (
    GLOBAL_GC_NAME,
    MAX_DAILY_DOUBT_POINTS,
    MAX_DAILY_DOUBT_REWARDS,
    POINTS_DOUBT_SOLVED,
    POINTS_MATERIAL_COMPLETED,
    POINTS_NOTE_SHARED,
    POINTS_QUIZ_COMPLETED,
    POINTS_RESOURCE_REVIEW,
    accept_doubt_solution,
    create_admin_adjustment,
    extract_text_from_upload,
    get_leaderboard,
    get_or_create_global_group,
    get_user_points_summary,
    get_user_streak_days,
    grade_quiz,
    learning_assist,
    parse_quiz_result,
    revoke_points_for_object,
    revoke_points_transaction,
    send_notification_email,
    send_password_reset_otp_email,
)

logger = logging.getLogger("hub")


def notify(user, text, link="", send_email=True):
    Notification.objects.create(user=user, text=text[:300], link=link)
    if send_email:
        send_notification_email(user, subject=text[:78], text=text, link=link)


def home(request):
    from django.contrib.auth import get_user_model
    from .models import DiscussionMessage

    User = get_user_model()
    return render(request, "hub/home.html", {
        "materials": StudyMaterial.objects.filter(is_published=True, is_flagged=False).select_related("owner").annotate(review_count=Count("reviews"))[:6],
        "groups": StudyGroup.objects.annotate(member_count=Count("members"))[:4],
        "total_materials": StudyMaterial.objects.filter(is_published=True, is_flagged=False).count(),
        "total_groups": StudyGroup.objects.count(),
        "total_messages": DiscussionMessage.objects.count(),
        "total_users": User.objects.count(),
        "top_contributors": get_leaderboard(limit=3),
    })


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to StudySphere — your workspace is ready.")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    global_group = get_or_create_global_group(request.user)
    recent = StudyMaterial.objects.filter(owner=request.user)[:5]
    other_users_notes = (
        StudyMaterial.objects.filter(is_published=True, is_flagged=False)
        .exclude(owner=request.user)
        .select_related("owner")[:8]
    )
    all_shared_notes = (
        StudyMaterial.objects.filter(is_published=True, is_flagged=False)
        .select_related("owner")[:8]
    )
    progress = LearningProgress.objects.filter(user=request.user).select_related("material")[:5]
    due_reviews = LearningProgress.objects.filter(user=request.user, review_due_at__lte=timezone.now()).select_related("material")[:5]
    full_board = get_leaderboard(limit=50)
    my_rank_entry = next((item for item in full_board if item["user"].pk == request.user.pk), None)
    streak_days = get_user_streak_days(request.user)
    recent_notifications = request.user.notifications.all()[:4]
    group_invitations = StudyGroup.objects.exclude(members=request.user).annotate(member_count=Count("members"))[:3]
    latest_gc_messages = (
        list(reversed(global_group.messages.select_related("author").order_by("-created_at")[:3]))
        if global_group else []
    )

    return render(request, "hub/dashboard.html", {
        "my_material_count": StudyMaterial.objects.filter(owner=request.user).count(),
        "group_count": request.user.study_groups.count(),
        "completed_count": LearningProgress.objects.filter(user=request.user, completed=True).count(),
        "recent_materials": recent,
        "other_users_notes": other_users_notes,
        "all_shared_notes": all_shared_notes,
        "share_form": MaterialForm(),
        "global_group": global_group,
        "global_messages": global_group.messages.select_related("author").all() if global_group else [],
        "latest_gc_messages": latest_gc_messages,
        "message_form": MessageForm(),
        "leaderboard": full_board[:8],
        "my_rank_entry": my_rank_entry,
        "streak_days": streak_days,
        "recent_notifications": recent_notifications,
        "group_invitations": group_invitations,
        "progress": progress,
        "due_reviews": due_reviews,
        "saved_materials": SavedMaterial.objects.filter(user=request.user).select_related("material", "collection")[:5],
        "quiz_average": request.user.quiz_attempts.aggregate(average=Avg("score"))["average"],
    })


def material_list(request):
    query = request.GET.get("q", "").strip()
    subject = request.GET.get("subject", "").strip()
    materials = StudyMaterial.objects.filter(is_published=True, is_flagged=False).select_related("owner").all()
    if query:
        materials = materials.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(topic__icontains=query))
    if subject:
        materials = materials.filter(subject__iexact=subject)
    subjects = StudyMaterial.objects.order_by("subject").values_list("subject", flat=True).distinct()
    return render(request, "hub/material_list.html", {"materials": materials, "subjects": subjects, "query": query, "selected_subject": subject})


def material_detail(request, pk):
    material = get_object_or_404(StudyMaterial.objects.select_related("owner"), pk=pk)
    if request.user.is_authenticated:
        LearningProgress.objects.get_or_create(user=request.user, material=material)
    is_saved = request.user.is_authenticated and SavedMaterial.objects.filter(user=request.user, material=material).exists()
    return render(request, "hub/material_detail_v2.html", {"material": material, "review_form": ReviewForm(), "report_form": ReportForm(), "is_saved": is_saved})


@login_required
def material_create(request):
    form = MaterialForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        material = form.save(commit=False)
        material.owner = request.user
        if material.file:
            material.extracted_text = extract_text_from_upload(material.file)
            material.file.seek(0)
        material.save()
        active_profiles = (
            Profile.objects.filter(email_notifications=True)
            .exclude(user=request.user)
            .select_related("user")
        )
        for prof in active_profiles:
            notify(
                prof.user,
                f"@{request.user.username} shared new {material.get_material_type_display()}: \u201c{material.title}\u201d ({material.subject}).",
                material.get_absolute_url(),
                send_email=True,
            )
        messages.success(request, "Your study material has been published (+25 Leaderboard pts!).")
        if request.POST.get("next") == "dashboard":
            return redirect("dashboard")
        return redirect(material)
    return render(request, "hub/form_page.html", {"form": form, "title": "Share a study resource", "submit_label": "Publish resource"})


@login_required
def material_edit(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk, owner=request.user)
    form = MaterialForm(request.POST or None, request.FILES or None, instance=material)
    if request.method == "POST" and form.is_valid():
        material = form.save(commit=False)
        if "file" in form.changed_data and material.file:
            material.extracted_text = extract_text_from_upload(material.file)
            material.file.seek(0)
        material.save()
        messages.success(request, "Resource updated.")
        return redirect(material)
    return render(request, "hub/form_page.html", {"form": form, "title": "Edit study resource", "submit_label": "Save changes"})


@login_required
@require_POST
def material_delete(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk, owner=request.user)
    material.delete()
    messages.success(request, "Resource deleted.")
    return redirect("material_list")


@login_required
@require_POST
def review_material(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk)
    form = ReviewForm(request.POST)
    if form.is_valid():
        MaterialReview.objects.update_or_create(material=material, author=request.user, defaults=form.cleaned_data)
        if material.owner != request.user:
            notify(material.owner, f"{request.user.username} reviewed \u201c{material.title}\u201d.", material.get_absolute_url())
        messages.success(request, "Thanks — your review has been saved.")
    return redirect(material)


@login_required
@require_POST
def toggle_saved(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk)
    saved, created = SavedMaterial.objects.get_or_create(user=request.user, material=material)
    if created:
        messages.success(request, "Saved to your learning list.")
    else:
        saved.delete()
        messages.success(request, "Removed from your learning list.")
    return redirect(material)


@login_required
@require_POST
def report_material(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk)
    form = ReportForm(request.POST)
    if form.is_valid():
        ContentReport.objects.create(material=material, reporter=request.user, **form.cleaned_data)
        messages.success(request, "Report received. A moderator can review it from the admin area.")
    return redirect(material)


def _get_user_active_custom_group(user):
    if not user or not user.is_authenticated:
        return None
    return (
        StudyGroup.objects.exclude(name=GLOBAL_GC_NAME)
        .filter(members=user)
        .select_related("owner")
        .order_by("-created_at")
        .first()
    )


def group_list(request):
    """Collaborate Hub: If the user is already in a custom study group, take them directly
    to their group workspace. Otherwise show the clean Create Group / Join Group page."""
    for g in StudyGroup.objects.filter(Q(group_code__isnull=True) | Q(group_code="")):
        g.save()

    if request.user.is_authenticated:
        active_group = _get_user_active_custom_group(request.user)
        if active_group:
            return redirect("group_detail", pk=active_group.pk)

    pending_invitations = []
    my_pending_join_requests = []

    if request.user.is_authenticated:
        pending_invitations = (
            GroupAccessRequest.objects.filter(
                user=request.user,
                request_type=GroupAccessRequest.RequestType.INVITATION,
                status=GroupAccessRequest.Status.PENDING,
            )
            .select_related("group", "group__owner", "invited_by")
        )
        my_pending_join_requests = (
            GroupAccessRequest.objects.filter(
                user=request.user,
                request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
                status=GroupAccessRequest.Status.PENDING,
            )
            .select_related("group", "group__owner")
        )

    return render(
        request,
        "hub/group_list.html",
        {
            "pending_invitations": pending_invitations,
            "my_pending_join_requests": my_pending_join_requests,
            "create_form": GroupForm(),
        },
    )


@login_required
def group_create(request):
    active_group = _get_user_active_custom_group(request.user)
    if active_group:
        messages.error(
            request,
            "You are already in a group. Leave or delete your current group before creating a new one.",
        )
        return redirect("group_detail", pk=active_group.pk)

    form = GroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.owner = request.user
        if not group.subject:
            group.subject = "General"
        group.save()
        GroupMembership.objects.get_or_create(group=group, user=request.user)
        return redirect("group_detail", pk=group.pk)
    return render(request, "hub/form_page.html", {"form": form, "title": "Create a study group", "submit_label": "Create group"})


def _build_group_chat_context(request, group, is_member, is_global_gc):
    if not group.group_code:
        group.save()

    active_tab = request.GET.get("tab", "general").strip().lower()
    if active_tab not in ("general", "doubts"):
        active_tab = "general"

    general_messages = group.messages.select_related("author", "reply_to", "reply_to__author").all() if is_member else []
    doubts = (
        group.doubts.select_related("author", "solved_by", "accepted_reply")
        .prefetch_related("replies__author")
        .annotate(reply_count=Count("replies"))
        .all()
        if is_member
        else []
    )
    default_subject = group.subject if not is_global_gc else "Computer Science"
    is_group_admin = request.user.is_authenticated and (group.owner_id == request.user.pk or request.user.is_staff)
    pending_group_requests = (
        group.access_requests.filter(
            request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
            status=GroupAccessRequest.Status.PENDING,
        ).select_related("user")
        if is_group_admin
        else []
    )
    user_has_pending_request = (
        request.user.is_authenticated
        and group.access_requests.filter(
            user=request.user,
            request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
            status=GroupAccessRequest.Status.PENDING,
        ).exists()
    )
    user_pending_invitation = (
        group.access_requests.filter(
            user=request.user,
            request_type=GroupAccessRequest.RequestType.INVITATION,
            status=GroupAccessRequest.Status.PENDING,
        ).first()
        if request.user.is_authenticated
        else None
    )
    other_members = (
        group.members.exclude(pk=request.user.pk).order_by("username")
        if request.user.is_authenticated
        else group.members.none()
    )

    return {
        "group": group,
        "is_member": is_member,
        "is_global_gc": is_global_gc,
        "is_group_admin": is_group_admin,
        "pending_group_requests": pending_group_requests,
        "user_has_pending_request": user_has_pending_request,
        "user_pending_invitation": user_pending_invitation,
        "group_members": group.members.all(),
        "other_members": other_members,
        "active_tab": active_tab,
        "general_messages": general_messages,
        "doubts": doubts,
        "unresolved_doubt_count": group.doubts.filter(is_resolved=False).count() if is_member else 0,
        "resolved_doubt_count": group.doubts.filter(is_resolved=True).count() if is_member else 0,
        "message_form": MessageForm(),
        "doubt_form": AcademicDoubtForm(initial={"subject": default_subject}),
        "reply_form": DoubtReplyForm(),
    }


def group_detail(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if request.user.is_authenticated and group.name == GLOBAL_GC_NAME:
        GroupMembership.objects.get_or_create(group=group, user=request.user)
    is_member = request.user.is_authenticated and group.members.filter(pk=request.user.pk).exists()
    ctx = _build_group_chat_context(request, group, is_member, group.name == GLOBAL_GC_NAME)
    return render(request, "hub/group_detail_v2.html", ctx)


@login_required
def global_chat(request):
    """Default Global Group Chat with General Talk (0 pts) and Academic Doubts (+20 pts for accepted solution)."""
    group = get_or_create_global_group(request.user)
    ctx = _build_group_chat_context(request, group, True, True)
    return render(request, "hub/group_detail_v2.html", ctx)


def leaderboard_view(request):
    """Community Leaderboard ranking users by approved notes, accepted doubt solutions, and learning activity."""
    board = get_leaderboard(limit=50)
    my_rank_entry = None
    my_summary = None
    if request.user.is_authenticated:
        my_rank_entry = next((item for item in board if item["user"].pk == request.user.pk), None)
        my_summary = get_user_points_summary(request.user)
    active_tab = request.GET.get("tab", "leaderboard").strip().lower()
    if active_tab not in ("leaderboard", "earn"):
        active_tab = "leaderboard"
    return render(request, "hub/leaderboard.html", {
        "leaderboard": board,
        "top_three": board[:3],
        "my_rank_entry": my_rank_entry,
        "my_summary": my_summary,
        "active_tab": active_tab,
        "max_daily_doubt_rewards": MAX_DAILY_DOUBT_REWARDS,
        "max_daily_doubt_points": MAX_DAILY_DOUBT_POINTS,
    })


@login_required
def points_history_view(request):
    """Dedicated Points History ledger page showing a student's earned, deducted, and net points."""
    User = get_user_model()
    requested_user_id = request.GET.get("user_id", "").strip()
    target_user = request.user
    if requested_user_id:
        if str(request.user.pk) != requested_user_id and not request.user.is_staff:
            return HttpResponseForbidden("You are not authorized to view another student's points history.")
        target_user = get_object_or_404(User, pk=requested_user_id)

    summary = get_user_points_summary(target_user)
    qs = PointsTransaction.objects.filter(user=target_user).order_by("-created_at", "-id")

    activity_type = request.GET.get("activity_type", "").strip()
    status_filter = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    search_q = request.GET.get("q", "").strip()

    if activity_type:
        qs = qs.filter(activity_type=activity_type)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if search_q:
        qs = qs.filter(Q(description__icontains=search_q) | Q(revoked_reason__icontains=search_q))

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return render(request, "hub/points_history.html", {
        "target_user": target_user,
        "summary": summary,
        "page_obj": page_obj,
        "transactions": page_obj.object_list,
        "activity_choices": PointsTransaction.ActivityType.choices,
        "status_choices": PointsTransaction.Status.choices,
        "selected_activity": activity_type,
        "selected_status": status_filter,
        "date_from": date_from,
        "date_to": date_to,
        "search_q": search_q,
    })


@login_required
@require_POST
def join_group(request, pk):
    """Send a join request to a group (requires Admin approval unless Global GC or already invited)."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.name == GLOBAL_GC_NAME or group.owner_id == request.user.pk:
        GroupMembership.objects.get_or_create(group=group, user=request.user)
        return redirect("group_detail", pk=pk)

    active_group = _get_user_active_custom_group(request.user)
    if active_group and active_group.pk != group.pk:
        messages.error(request, "You are already in a group. Leave or delete your current group before joining another one.")
        return redirect("group_detail", pk=active_group.pk)

    if group.members.filter(pk=request.user.pk).exists():
        return redirect("group_detail", pk=pk)

    existing_invite = GroupAccessRequest.objects.filter(
        group=group,
        user=request.user,
        request_type=GroupAccessRequest.RequestType.INVITATION,
        status=GroupAccessRequest.Status.PENDING,
    ).first()
    if existing_invite:
        existing_invite.status = GroupAccessRequest.Status.ACCEPTED
        existing_invite.save(update_fields=["status", "updated_at"])
        GroupMembership.objects.get_or_create(group=group, user=request.user)
        return redirect("group_detail", pk=pk)

    GroupAccessRequest.objects.update_or_create(
        group=group,
        user=request.user,
        request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
        defaults={"status": GroupAccessRequest.Status.PENDING},
    )
    notify(
        group.owner,
        f"@{request.user.username} requested to join your group “{group.name}”.",
        f"/groups/{group.pk}/",
        send_email=False,
    )
    messages.success(request, f"Join request sent to @{group.owner.username}.")
    return redirect("group_list")


@login_required
@require_POST
def request_join_by_code(request):
    """Join a group by entering its Unique Group ID (e.g. SS-7F3K9A). Creates a join request for Admin approval."""
    active_group = _get_user_active_custom_group(request.user)
    if active_group:
        messages.error(request, "You are already in a group. Leave or delete your current group before joining another one.")
        return redirect("group_detail", pk=active_group.pk)

    raw_code = request.POST.get("group_code", "").strip().upper()
    if not raw_code:
        messages.error(request, "Please enter a valid Group ID.")
        return redirect("group_list")

    normalized = raw_code if raw_code.startswith("SS-") else f"SS-{raw_code}"
    group = StudyGroup.objects.filter(
        Q(group_code__iexact=raw_code) | Q(group_code__iexact=normalized)
    ).exclude(name=GLOBAL_GC_NAME).first()
    if not group and raw_code.isdigit():
        group = StudyGroup.objects.filter(pk=int(raw_code)).exclude(name=GLOBAL_GC_NAME).first()

    if not group:
        messages.error(request, f"No group found with Group ID “{raw_code}”.")
        return redirect("group_list")

    if group.members.filter(pk=request.user.pk).exists():
        return redirect("group_detail", pk=group.pk)

    existing_invite = GroupAccessRequest.objects.filter(
        group=group,
        user=request.user,
        request_type=GroupAccessRequest.RequestType.INVITATION,
        status=GroupAccessRequest.Status.PENDING,
    ).first()
    if existing_invite:
        existing_invite.status = GroupAccessRequest.Status.ACCEPTED
        existing_invite.save(update_fields=["status", "updated_at"])
        GroupMembership.objects.get_or_create(group=group, user=request.user)
        return redirect("group_detail", pk=group.pk)

    GroupAccessRequest.objects.update_or_create(
        group=group,
        user=request.user,
        request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
        defaults={"status": GroupAccessRequest.Status.PENDING},
    )
    notify(
        group.owner,
        f"@{request.user.username} requested to join your group “{group.name}”.",
        f"/groups/{group.pk}/",
        send_email=False,
    )
    messages.success(request, f"Join request sent for “{group.name}”. Waiting for Admin @{group.owner.username} to accept.")
    return redirect("group_list")


@login_required
@require_POST
def invite_to_group(request, pk):
    """Invite a student to a group by their @username."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.owner_id != request.user.pk and not group.members.filter(pk=request.user.pk).exists() and not request.user.is_staff:
        return HttpResponseForbidden("Only group members or the group admin can invite students.")

    raw_username = request.POST.get("username", "").strip().lstrip("@")
    redirect_to = redirect("group_detail", pk=group.pk)

    if not raw_username:
        messages.error(request, "Please enter a username to invite.")
        return redirect_to

    User = get_user_model()
    target_user = User.objects.filter(username__iexact=raw_username).first()
    if not target_user:
        messages.error(request, f"No student account found with username @{raw_username}.")
        return redirect_to

    if group.members.filter(pk=target_user.pk).exists():
        messages.info(request, f"@{target_user.username} is already a member.")
        return redirect_to

    pending_join = GroupAccessRequest.objects.filter(
        group=group,
        user=target_user,
        request_type=GroupAccessRequest.RequestType.JOIN_REQUEST,
        status=GroupAccessRequest.Status.PENDING,
    ).first()
    if pending_join and (group.owner_id == request.user.pk or request.user.is_staff):
        pending_join.status = GroupAccessRequest.Status.ACCEPTED
        pending_join.save(update_fields=["status", "updated_at"])
        GroupMembership.objects.get_or_create(group=group, user=target_user)
        notify(
            target_user,
            f"@{request.user.username} added you to study group “{group.name}”!",
            f"/groups/{group.pk}/",
            send_email=False,
        )
        messages.success(request, f"@{target_user.username} added to the group!")
        return redirect_to

    GroupAccessRequest.objects.update_or_create(
        group=group,
        user=target_user,
        request_type=GroupAccessRequest.RequestType.INVITATION,
        defaults={
            "invited_by": request.user,
            "status": GroupAccessRequest.Status.PENDING,
        },
    )
    notify(
        target_user,
        f"@{request.user.username} invited you to join study group “{group.name}”.",
        "/groups/",
        send_email=False,
    )
    messages.success(request, f"Invitation sent to @{target_user.username}.")
    return redirect_to


@login_required
@require_POST
def respond_group_access_request(request, req_pk):
    """Allow a group Admin to accept/reject a join request, OR an invited user to accept/decline an invitation."""
    access_req = get_object_or_404(
        GroupAccessRequest.objects.select_related("group", "user", "group__owner"),
        pk=req_pk,
    )
    action = request.POST.get("action", "accept").strip().lower()
    group = access_req.group

    if access_req.request_type == GroupAccessRequest.RequestType.JOIN_REQUEST:
        if group.owner_id != request.user.pk and not request.user.is_staff:
            return HttpResponseForbidden("Only the group admin can approve or decline join requests.")
        if action == "accept":
            access_req.status = GroupAccessRequest.Status.ACCEPTED
            access_req.save(update_fields=["status", "updated_at"])
            GroupMembership.objects.get_or_create(group=group, user=access_req.user)
            notify(
                access_req.user,
                f"Admin @{request.user.username} accepted your request to join “{group.name}”!",
                f"/groups/{group.pk}/",
                send_email=False,
            )
            messages.success(request, f"Accepted @{access_req.user.username} into the group.")
        else:
            access_req.status = GroupAccessRequest.Status.REJECTED
            access_req.save(update_fields=["status", "updated_at"])
            messages.info(request, f"Declined join request from @{access_req.user.username}.")
        return redirect("group_detail", pk=group.pk)

    # INVITATION response by the invited user
    if access_req.user_id != request.user.pk:
        return HttpResponseForbidden("Only the invited student can respond to this invitation.")
    if action == "accept":
        active_group = _get_user_active_custom_group(request.user)
        if active_group and active_group.pk != group.pk:
            messages.error(request, "You are already in a group. Leave or delete your current group before joining another one.")
            return redirect("group_detail", pk=active_group.pk)
        access_req.status = GroupAccessRequest.Status.ACCEPTED
        access_req.save(update_fields=["status", "updated_at"])
        GroupMembership.objects.get_or_create(group=group, user=request.user)
        notify(
            group.owner,
            f"@{request.user.username} accepted your invitation and joined “{group.name}”!",
            f"/groups/{group.pk}/",
            send_email=False,
        )
        return redirect("group_detail", pk=group.pk)
    else:
        access_req.status = GroupAccessRequest.Status.REJECTED
        access_req.save(update_fields=["status", "updated_at"])
        return redirect("group_list")


@login_required
@require_POST
def leave_group(request, pk):
    """Allow a member to leave their group. If the user is the Group Admin, require them
    to either transfer Admin to another member first or delete the group."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.name == GLOBAL_GC_NAME:
        return redirect("dashboard")

    if group.owner_id == request.user.pk:
        messages.error(
            request,
            "As the Group Admin, please transfer Admin to another member before leaving, or delete the group.",
        )
        return redirect("group_detail", pk=group.pk)

    GroupMembership.objects.filter(group=group, user=request.user).delete()
    GroupAccessRequest.objects.filter(group=group, user=request.user).delete()
    messages.info(request, f"You left “{group.name}”.")
    return redirect("group_list")


@login_required
@require_POST
def transfer_group_admin(request, pk):
    """Transfer Group Admin (owner) role to another member of the group."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.owner_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("Only the Group Admin can transfer admin rights.")

    new_admin_id = request.POST.get("new_admin_id", "").strip()
    if not new_admin_id.isdigit():
        messages.error(request, "Please select a group member to transfer Admin to.")
        return redirect("group_detail", pk=group.pk)

    new_admin = group.members.filter(pk=int(new_admin_id)).exclude(pk=request.user.pk).first()
    if not new_admin:
        messages.error(request, "Selected user is not a member of this group.")
        return redirect("group_detail", pk=group.pk)

    group.owner = new_admin
    group.save(update_fields=["owner"])
    notify(
        new_admin,
        f"@{request.user.username} made you the Group Admin of “{group.name}”.",
        f"/groups/{group.pk}/",
        send_email=False,
    )

    if request.POST.get("and_leave") == "1":
        GroupMembership.objects.filter(group=group, user=request.user).delete()
        GroupAccessRequest.objects.filter(group=group, user=request.user).delete()
        messages.success(request, f"Transferred Admin to @{new_admin.username} and left “{group.name}”.")
        return redirect("group_list")

    messages.success(request, f"@{new_admin.username} is now the Group Admin.")
    return redirect("group_detail", pk=group.pk)


@login_required
@require_POST
def delete_group(request, pk):
    """Allow the Group Admin to delete the group completely."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.name == GLOBAL_GC_NAME:
        return HttpResponseForbidden("The default campus group cannot be deleted.")
    if group.owner_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("Only the Group Admin can delete this group.")

    group_name = group.name
    group.delete()
    messages.info(request, f"Group “{group_name}” was deleted.")
    return redirect("group_list")


@login_required
@require_POST
def post_message(request, pk):
    """Post a message in Tab A: General Talk (0 points)."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.name == GLOBAL_GC_NAME:
        GroupMembership.objects.get_or_create(group=group, user=request.user)
    elif not group.members.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("Join this group before posting.")
    form = MessageForm(request.POST)
    if form.is_valid():
        message = form.save(commit=False)
        message.group, message.author = group, request.user
        reply_to_id = request.POST.get("reply_to")
        if reply_to_id and reply_to_id.isdigit():
            message.reply_to = DiscussionMessage.objects.filter(pk=int(reply_to_id), group=group).first()
        message.save()
        for member in group.members.exclude(pk=request.user.pk):
            notify(
                member,
                f"New message in {group.name} from {request.user.username}.",
                f"/groups/{group.pk}/?tab=general",
                send_email=False,
            )
    if request.POST.get("next") == "dashboard":
        messages.success(request, "Message posted to General Talk.")
        return redirect("dashboard")
    return redirect("group_detail", pk=pk)


@login_required
@require_POST
def delete_message(request, msg_pk):
    """Allow a user (or staff moderator) to delete their own message in General Talk."""
    message = get_object_or_404(DiscussionMessage.objects.select_related("group", "author"), pk=msg_pk)
    if message.author_id != request.user.pk and not request.user.is_staff:
        return HttpResponseForbidden("You can only delete your own messages.")
    if message.is_system and not request.user.is_staff:
        return HttpResponseForbidden("System messages cannot be deleted.")

    group_pk = message.group_id
    message.delete()

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": True, "deleted_id": msg_pk})

    messages.success(request, "Your message was deleted.")
    return redirect(f"/groups/{group_pk}/?tab=general")


@login_required
@require_POST
def create_doubt(request, pk):
    """Create a new academic doubt in Tab B: Academic Doubts (0 points for asking)."""
    group = get_object_or_404(StudyGroup, pk=pk)
    if group.name == GLOBAL_GC_NAME:
        GroupMembership.objects.get_or_create(group=group, user=request.user)
    elif not group.members.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("Join this group before posting an academic doubt.")

    post_data = request.POST.copy()
    raw_body = post_data.get("body", "").strip()
    if raw_body and not post_data.get("title", "").strip():
        first_line = raw_body.splitlines()[0].strip()
        post_data["title"] = (first_line[:120] if first_line else raw_body[:120])
    if not post_data.get("subject", "").strip():
        post_data["subject"] = group.subject if group.name != GLOBAL_GC_NAME else "General"

    form = AcademicDoubtForm(post_data)
    if form.is_valid():
        doubt = form.save(commit=False)
        doubt.group = group
        doubt.author = request.user
        doubt.save()

        # Notify tagged student if specified
        User = get_user_model()
        notified_ids = {request.user.pk}
        tagged_names = set(re.findall(r"@([A-Za-z0-9_.\-]+)", doubt.body or ""))
        if doubt.tagged_username:
            tagged_names.add(doubt.tagged_username.lstrip("@"))

        for uname in tagged_names:
            tagged_user = User.objects.filter(username__iexact=uname).first()
            if tagged_user and tagged_user.pk not in notified_ids:
                notify(
                    tagged_user,
                    f"@{request.user.username} tagged you in an academic doubt: “{doubt.title[:90]}”.",
                    f"/groups/{group.pk}/?tab=doubts#doubt-{doubt.pk}",
                )
                notified_ids.add(tagged_user.pk)

        for member in group.members.exclude(pk__in=notified_ids):
            notify(
                member,
                f"New academic doubt in {group.name}: “{doubt.title[:90]}”.",
                f"/groups/{group.pk}/?tab=doubts#doubt-{doubt.pk}",
            )
        messages.success(request, "Your academic doubt has been posted. Accept a helpful peer explanation to award +20 pts!")
    else:
        messages.error(request, "Please fill in a valid doubt title and description.")
    return redirect(f"/groups/{group.pk}/?tab=doubts")


@login_required
@require_POST
def reply_doubt(request, doubt_pk):
    """Post an explanation/reply to an existing AcademicDoubt (0 points until accepted)."""
    doubt = get_object_or_404(AcademicDoubt.objects.select_related("group", "author"), pk=doubt_pk)
    group = doubt.group
    if group.name == GLOBAL_GC_NAME:
        GroupMembership.objects.get_or_create(group=group, user=request.user)
    elif not group.members.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("Join this group before replying to an academic doubt.")

    form = DoubtReplyForm(request.POST)
    if form.is_valid():
        reply = form.save(commit=False)
        reply.doubt = doubt
        reply.author = request.user
        reply.save()

        if doubt.author_id != request.user.pk:
            notify(
                doubt.author,
                f"@{request.user.username} replied to your academic doubt “{doubt.title[:90]}”.",
                f"/groups/{group.pk}/?tab=doubts#doubt-{doubt.pk}",
            )
        messages.success(request, "Your explanation has been posted. If accepted as the solution, you will earn +20 Leaderboard points!")
    else:
        messages.error(request, "Please enter a valid reply.")
    return redirect(f"/groups/{group.pk}/?tab=doubts#doubt-{doubt.pk}")


@login_required
@require_POST
def accept_doubt_reply_view(request, doubt_pk, reply_pk):
    """Accept a reply as the verified solution for an AcademicDoubt (+20 pts to reply author)."""
    doubt = get_object_or_404(AcademicDoubt, pk=doubt_pk)
    success, msg, _ = accept_doubt_solution(doubt_id=doubt.pk, reply_id=reply_pk, acting_user=request.user)
    if success:
        messages.success(request, msg)
    else:
        messages.error(request, msg)
    return redirect(f"/groups/{doubt.group_id}/?tab=doubts#doubt-{doubt.pk}")


@login_required
@require_POST
def revoke_doubt_reward_view(request, doubt_pk):
    """Moderator action to revoke the +20 point reward on a flagged/fraudulent academic doubt solution."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    doubt = get_object_or_404(AcademicDoubt, pk=doubt_pk)
    reason = request.POST.get("reason", "Solution flagged or revoked by moderator").strip()
    reversal_tx, revoked = revoke_points_for_object(
        "AcademicDoubt",
        doubt.pk,
        reason=reason,
        moderator=request.user,
    )
    if revoked:
        doubt.reward_revoked = True
        doubt.save(update_fields=["reward_revoked", "updated_at"])
        if doubt.solved_by:
            notify(
                doubt.solved_by,
                f"A moderator revoked the +{POINTS_DOUBT_SOLVED} pts reward on “{doubt.title[:80]}” ({reason}).",
                "/points-history/",
            )
        messages.success(request, "Doubt solution reward (-20 pts) has been revoked and recorded in the points ledger.")
    else:
        messages.error(request, "No active reward found to revoke for this doubt.")
    return redirect(f"/groups/{doubt.group_id}/?tab=doubts#doubt-{doubt.pk}")


@login_required
@require_POST
def revoke_transaction_view(request, tx_pk):
    """Staff-only endpoint to revoke any approved positive PointsTransaction with a recorded reason."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    tx = get_object_or_404(PointsTransaction, pk=tx_pk)
    reason = request.POST.get("reason", "Revoked by staff moderator").strip()
    _, revoked = revoke_points_transaction(tx, reason=reason, moderator=request.user)
    if revoked:
        notify(tx.user, f"A reward ({tx.points} pts) was revoked by a moderator: {reason}", "/points-history/")
        messages.success(request, f"Transaction #{tx.pk} revoked and reversal entry recorded.")
    else:
        messages.error(request, "Transaction is already revoked or cannot be reversed.")
    return redirect(f"/points-history/?user_id={tx.user_id}")


@login_required
@require_POST
def admin_adjust_points_view(request):
    """Staff-only endpoint to record an authorized point adjustment with a reason."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    User = get_user_model()
    target_user = get_object_or_404(User, pk=request.POST.get("user_id"))
    try:
        points = int(request.POST.get("points", "0"))
    except ValueError:
        messages.error(request, "Enter a valid integer point adjustment.")
        return redirect("leaderboard")
    reason = request.POST.get("reason", "Authorized moderator adjustment").strip()
    _, created = create_admin_adjustment(target_user, points, reason, moderator=request.user)
    if created:
        messages.success(request, f"Recorded {points:+d} pts adjustment for @{target_user.username}.")
    return redirect(f"/points-history/?user_id={target_user.pk}")


@login_required
def ai_studio(request):
    result = None
    source = ""
    action = "summary"
    quiz_data = None
    materials = StudyMaterial.objects.filter(Q(owner=request.user) | Q(is_published=True, is_flagged=False)).distinct()
    if request.method == "POST":
        source = request.POST.get("source", "").strip()
        material_id = request.POST.get("material_id")
        if material_id and not source:
            selected = get_object_or_404(materials, pk=material_id)
            source = selected.extracted_text or selected.description
        action = request.POST.get("action", "summary")
        if source:
            today = timezone.localdate()
            if AIUsage.objects.filter(user=request.user, created_at__date=today).count() >= settings.AI_DAILY_REQUEST_LIMIT:
                messages.error(request, "You have reached today's AI Study Studio limit. Try again tomorrow.")
            else:
                result, provider = learning_assist(source, action)
                AIUsage.objects.create(user=request.user, action=action, provider=provider, input_characters=len(source), output_characters=len(result))
                # If this is a quiz, try parsing structured data for auto-grading
                if action == "quiz":
                    quiz_data = parse_quiz_result(result)
                    if quiz_data:
                        request.session["pending_quiz"] = result
        else:
            messages.error(request, "Paste study text first.")
    return render(request, "hub/ai_studio_v2.html", {
        "result": result, "source": source, "action": action,
        "materials": materials, "quiz_data": quiz_data,
    })


@login_required
@require_POST
def grade_quiz_view(request):
    """Auto-grade a quiz from session data and user-submitted answers."""
    quiz_json = request.session.pop("pending_quiz", None)
    if not quiz_json:
        messages.error(request, "No quiz to grade. Generate a quiz first.")
        return redirect("ai_studio")
    quiz_data = parse_quiz_result(quiz_json)
    if not quiz_data:
        messages.error(request, "Could not parse quiz data.")
        return redirect("ai_studio")
    user_answers = {}
    for i in range(len(quiz_data)):
        user_answers[str(i)] = request.POST.get(f"answer_{i}", "")
    score_percent, total, correct, results = grade_quiz(quiz_data, user_answers)
    QuizAttempt.objects.create(user=request.user, score=score_percent, title="AI auto-graded quiz")
    return render(request, "hub/quiz_results.html", {
        "score": score_percent, "total": total, "correct": correct, "results": results,
    })


@login_required
@require_POST
def toggle_progress(request, pk):
    material = get_object_or_404(StudyMaterial, pk=pk)
    progress, _ = LearningProgress.objects.get_or_create(user=request.user, material=material)
    if progress.completed:
        progress.completed, progress.review_due_at, progress.review_interval_days = False, None, 1
        progress.save(update_fields=["completed", "review_due_at", "review_interval_days", "last_opened_at"])
    else:
        progress.complete_and_schedule()
    return redirect(material)


@login_required
def profile_edit(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("dashboard")
    return render(request, "hub/form_page.html", {"form": form, "title": "Edit your profile", "submit_label": "Save profile"})


@login_required
def saved_materials(request):
    saved = SavedMaterial.objects.filter(user=request.user).select_related("material", "collection")
    collections = StudyCollection.objects.filter(user=request.user)
    return render(request, "hub/saved_materials.html", {"saved": saved, "collections": collections, "collection_form": CollectionForm()})


@login_required
@require_POST
def collection_create(request):
    form = CollectionForm(request.POST)
    if form.is_valid():
        StudyCollection.objects.get_or_create(user=request.user, name=form.cleaned_data["name"], defaults={"description": form.cleaned_data["description"]})
    return redirect("saved_materials")


@login_required
@require_POST
def update_saved_collection(request, pk):
    saved = get_object_or_404(SavedMaterial, pk=pk, user=request.user)
    collection_id = request.POST.get("collection_id")
    saved.collection = get_object_or_404(StudyCollection, pk=collection_id, user=request.user) if collection_id else None
    saved.save(update_fields=["collection"])
    return redirect("saved_materials")


@login_required
@require_POST
def record_quiz_score(request):
    try:
        score = int(request.POST.get("score", ""))
    except ValueError:
        messages.error(request, "Enter a whole-number score from 0 to 100.")
        return redirect("ai_studio")
    if not 0 <= score <= 100:
        messages.error(request, "Score must be between 0 and 100.")
        return redirect("ai_studio")
    QuizAttempt.objects.create(user=request.user, score=score, title=request.POST.get("title", "")[:180])
    messages.success(request, "Quiz score saved to your learning progress.")
    return redirect("dashboard")


@login_required
def notifications(request):
    items = request.user.notifications.all()
    items.filter(is_read=False).update(is_read=True)
    return render(request, "hub/notifications.html", {"notifications": items})


@login_required
@require_POST
def toggle_notifications(request):
    """Toggle ON/OFF email & shared-notes notifications from the top navbar bell widget."""
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.email_notifications = not profile.email_notifications
    profile.save(update_fields=["email_notifications"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": True, "enabled": profile.email_notifications})

    if profile.email_notifications:
        messages.success(request, "Notifications turned ON — you will receive email alerts when PDFs or study notes are shared.")
    else:
        messages.info(request, "Notifications turned OFF — email alerts are now muted.")

    next_url = request.POST.get("next", "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("dashboard")


@login_required
def moderation_queue(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    return render(request, "hub/moderation.html", {"reports": ContentReport.objects.filter(resolved=False).select_related("material", "reporter")})


@login_required
@require_POST
def resolve_report(request, pk):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    report = get_object_or_404(ContentReport, pk=pk)
    report.resolved = True
    report.save(update_fields=["resolved"])
    if request.POST.get("hide") == "1":
        report.material.is_flagged = True
        report.material.save(update_fields=["is_flagged"])
        notify(report.material.owner, f"Your resource \u201c{report.material.title}\u201d was hidden after a moderation report.")
    return redirect("moderation_queue")


# ---------------------------------------------------------------------------
# Health-check endpoint (for load balancers / uptime monitors)
# ---------------------------------------------------------------------------

def health_check(request):
    """Lightweight health-check endpoint for load balancers and monitoring."""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok}, status=status)


# ---------------------------------------------------------------------------
# Forgot Password via Email OTP (Request OTP -> Verify OTP -> Reset Password)
# ---------------------------------------------------------------------------

def forgot_password(request):
    """Step 1: User enters their registered email or username to receive a 6-digit OTP."""
    from datetime import timedelta
    import secrets
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        user = User.objects.filter(Q(email__iexact=identifier) | Q(username__iexact=identifier)).first()
        if not user or not user.email:
            messages.error(request, "No account with a registered email was found for that username or email.")
        else:
            otp_code = f"{secrets.randbelow(900000) + 100000}"
            expires_at = (timezone.now() + timedelta(minutes=10)).timestamp()
            request.session["password_reset_otp"] = {
                "user_id": user.pk,
                "email": user.email,
                "otp": otp_code,
                "expires_at": expires_at,
                "attempts": 0,
            }
            ok, err = send_password_reset_otp_email(user, otp_code)
            if not ok:
                messages.error(request, f"Could not send OTP email — check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in your .env file ({err}).")
                return render(request, "registration/forgot_password.html")
            messages.success(request, f"A 6-digit OTP has been sent to {user.email} (valid for 10 minutes).")
            return redirect("verify_reset_otp")
    return render(request, "registration/forgot_password.html")


def verify_reset_otp(request):
    """Step 2: User enters the 6-digit OTP sent to their email."""
    otp_data = request.session.get("password_reset_otp")
    if not otp_data:
        messages.error(request, "Please request a password reset OTP first.")
        return redirect("forgot_password")

    if request.method == "POST":
        if timezone.now().timestamp() > otp_data.get("expires_at", 0):
            request.session.pop("password_reset_otp", None)
            messages.error(request, "Your OTP has expired. Please request a new one.")
            return redirect("forgot_password")

        if otp_data.get("attempts", 0) >= 5:
            request.session.pop("password_reset_otp", None)
            messages.error(request, "Too many incorrect OTP attempts. Please request a new code.")
            return redirect("forgot_password")

        entered_otp = request.POST.get("otp", "").strip()
        if entered_otp == otp_data.get("otp"):
            request.session["otp_verified_user_id"] = otp_data["user_id"]
            request.session.pop("password_reset_otp", None)
            messages.success(request, "OTP verified! Set your new password below.")
            return redirect("reset_password_new")
        else:
            otp_data["attempts"] = otp_data.get("attempts", 0) + 1
            request.session["password_reset_otp"] = otp_data
            messages.error(request, "Invalid OTP code. Please check your email and try again.")

    return render(request, "registration/verify_otp.html", {
        "masked_email": otp_data.get("email", ""),
    })


def reset_password_new(request):
    """Step 3: After OTP verification, user sets their new password and is redirected to login."""
    from django.contrib.auth import get_user_model

    user_id = request.session.get("otp_verified_user_id")
    if not user_id:
        messages.error(request, "Please verify your OTP before resetting your password.")
        return redirect("forgot_password")

    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        p1 = request.POST.get("password1", "")
        p2 = request.POST.get("password2", "")
        if len(p1) < 6 or not re.search(r"[^A-Za-z0-9]", p1):
            messages.error(request, "Password must be at least 6 characters long and include at least one special character (e.g. @, #, $, !, -).")
        elif p1 != p2:
            messages.error(request, "Passwords do not match.")
        else:
            user.set_password(p1)
            user.save()
            request.session.pop("otp_verified_user_id", None)
            messages.success(request, "Your password has been reset! You can now sign in with your new password.")
            return redirect("login")

    return render(request, "registration/reset_password.html", {"reset_user": user})

