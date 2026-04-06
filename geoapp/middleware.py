from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone


class IPBanMiddleware:
    """Block requests from IP addresses listed in the IPBan table."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from geoapp.models import IPBan

        ip = self.get_client_ip(request)
        is_banned = IPBan.objects.filter(
            ip_address=ip,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).exists()

        if is_banned:
            return JsonResponse({"error": "Access denied."}, status=403)

        return self.get_response(request)

    @staticmethod
    def get_client_ip(request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
