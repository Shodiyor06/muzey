from django.urls import path
from . import views

urlpatterns = [
    path("enter/<str:key>/", views.enter),
    path("tg/webhook/<str:secret>/", views.webhook),
]
