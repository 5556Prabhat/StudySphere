import logging
import traceback
from django.http import JsonResponse

logger = logging.getLogger("hub")


class ErrorLoggingMiddleware:
    """Catches unhandled exceptions, logs full details, and returns a clean
    500 response in production. In DEBUG mode Django's own error page is shown."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        logger.error(
            "Unhandled exception on %s %s — %s: %s\nUser: %s\n%s",
            request.method,
            request.get_full_path(),
            type(exception).__name__,
            exception,
            getattr(request.user, "username", "anonymous"),
            traceback.format_exc(),
        )
        from django.conf import settings
        if not settings.DEBUG:
            return JsonResponse(
                {"error": "An internal server error occurred. Our team has been notified."},
                status=500,
            )
        return None  # Let Django's debug page handle it in dev

