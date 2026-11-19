def notification_context(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "notifications_enabled": False}
    profile = getattr(request.user, "profile", None)
    enabled = profile.email_notifications if profile is not None else True
    return {
        "unread_notification_count": request.user.notifications.filter(is_read=False).count(),
        "notifications_enabled": enabled,
    }
