import secrets
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone


class TgVisitor(models.Model):
    """Telegram orqali roʻyxatdan oʻtgan foydalanuvchi; ``user`` — uning profili."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                related_name="tg")
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
    KINDS = [("login", "Kirish"), ("visitor", "Mehmon (eski)"), ("invite", "Taklif (eski)")]
    key = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=10, choices=KINDS, default="login")
    visitor = models.ForeignKey(TgVisitor, null=True, blank=True, on_delete=models.CASCADE, related_name="tokens")
    label = models.CharField(max_length=80, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Boʻsh — muddatsiz.")
    uses = models.PositiveIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def valid(self):
        if self.revoked or (self.expires_at and self.expires_at <= timezone.now()):
            return False
        v = self.visitor
        return bool(v and v.user_id and not v.blocked and v.user.is_active)

    @classmethod
    def issue(cls, kind="login", days=None, visitor=None, label=""):
        """Yangi kalit. ``days`` berilmasa — muddatsiz (bot 2 kunlik havola yaratmaydi)."""
        return cls.objects.create(key=secrets.token_urlsafe(24), kind=kind, visitor=visitor, label=label[:80],
                                  expires_at=timezone.now() + timedelta(days=days) if days else None)
