from django.contrib import admin
from django.urls import include, path

from gallery.views import (config, guest, index, media, share_entry, sudo_enter,
                           telegram_admin, telegram_enter)

urlpatterns = [
    path("", include("access.urls")),
    path("admin/", include("gallery.panel_urls")),
    path("admin/django/", admin.site.urls),
    path("api/config/", config),
    path("api/guest/", guest),
    path("media/<path:path>", media),
    path("kirish/<str:token>/", share_entry, name="share_entry"),
    path("telegram/kirish/", telegram_enter, name="telegram_enter"),
    path("telegram/admin/", telegram_admin, name="telegram_admin"),
    path("telegram/boglash/", sudo_enter, name="telegram_bind"),
    path("", index),
]
