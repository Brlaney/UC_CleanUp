from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from geoapp.views import signup_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup/", signup_view, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("geoapp.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
