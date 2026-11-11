from django.core.management.base import BaseCommand
from gallery.purge import purge_expired, ttl_hours


class Command(BaseCommand):
    help = "Muddati oʻtgan rasmlarni bazadan va diskdan oʻchiradi (PHOTO_TTL_HOURS, standart 3 soat)."

    def add_arguments(self, p):
        p.add_argument("--hours", type=float)
        p.add_argument("--dry-run", action="store_true")

    def handle(self, *a, hours=None, dry_run=False, **k):
        n = purge_expired(hours, dry=dry_run)
        self.stdout.write(f"{'Oʻchiriladi' if dry_run else 'Oʻchirildi'}: {n} ta rasm (muddat: {hours if hours is not None else ttl_hours()} soat)")
