import secrets
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


class TgVisitor(models.Model):
    tg_id = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=120, blank=True)
    username = models.CharField(max_length=80, blank=True)
    blocked = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.first_name or self.username or str(self.tg_id)


class AccessToken(models.Model):
    KINDS = [("visitor", "Mehmon"), ("invite", "Taklif")]
    key = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=10, choices=KINDS, default="visitor")
    visitor = models.ForeignKey(TgVisitor, null=True, blank=True, on_delete=models.CASCADE, related_name="tokens")
    label = models.CharField(max_length=80, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    uses = models.PositiveIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def valid(self):
        return not self.revoked and self.expires_at > timezone.now() and not (self.visitor and self.visitor.blocked)

    @classmethod
    def issue(cls, kind, days=None, visitor=None, label=""):
        days = days or getattr(settings, "ACCESS_DAYS", 2)
        return cls.objects.create(key=secrets.token_urlsafe(24), kind=kind, visitor=visitor, label=label[:80],
                                  expires_at=timezone.now() + timedelta(days=days))
