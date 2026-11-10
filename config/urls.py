from django.contrib import admin
from django.urls import include, path

from gallery.views import (config, guest, index, logout_view, media, own_museum,
                           share_entry)

urlpatterns = [
    path("", include("access.urls")),
    path("admin/", include("gallery.panel_urls")),
    path("admin/django/", admin.site.urls),
    path("api/config/", config),
    path("api/guest/", guest),
    path("media/<path:path>", media),
    path("kirish/<str:token>/", share_entry, name="share_entry"),
    path("ozim/", own_museum, name="own_museum"),
    path("chiqish/", logout_view, name="logout"),
    path("", index),
]
