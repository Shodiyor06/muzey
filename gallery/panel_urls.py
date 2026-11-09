from django.urls import path

from . import panel

urlpatterns = [
    path("", panel.dashboard, name="panel"),
    path("rasmlar/", panel.photos, name="panel_photos"),
    path("rasmlar/yuklash/", panel.upload, name="panel_upload"),
    path("rasmlar/<int:pk>/", panel.photo_edit, name="panel_photo"),
    path("rasmlar/<int:pk>/ochirish/", panel.photo_delete, name="panel_photo_delete"),
    path("sozlamalar/", panel.settings_view, name="panel_settings"),
    path("sozlamalar/havola/", panel.share_action, name="panel_share"),
    path("xarita/", panel.map_editor, name="panel_map"),
    path("mehmonlar/", panel.guests, name="panel_guests"),
]
