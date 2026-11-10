import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image, ImageOps


class SiteSettings(models.Model):
    LAYOUTS = [("winding", "Burilishli yoʻlak"), ("cross", "Xoch zal"),
               ("ring", "Aylanma zal"), ("rooms", "Xonalar")]
    PALETTES = [("rose", "Atirgul"), ("night", "Tun"), ("gold", "Shampan"), ("green", "Zumrad")]
    title = models.CharField("Sarlavha", max_length=120, default="Bizning muzey")
    subtitle = models.TextField("Xat matni", default="Har bir surat — birga oʻtkazgan bir lahzamiz.")
    layout = models.CharField("Zal shakli", max_length=20, choices=LAYOUTS, default="winding",
                              help_text="Muzey rasmlar soniga qarab oʻzi uzayadi; shakl shu yerda tanlanadi.")
    palette = models.CharField("Devor rangi", max_length=20, choices=PALETTES, default="rose")
    telegram_id = models.BigIntegerField("Telegram ID", null=True, blank=True,
                                        help_text="Muzeyga faqat shu Telegram akkaunt egasi kira oladi. ID ni @userinfobot orqali bilib oling.")
    telegram_bot = models.CharField("Telegram bot username", max_length=64, blank=True,
                                    help_text="Masalan: mening_muzey_bot — @ belgisisiz.")
    telegram_token = models.CharField("Telegram bot token", max_length=200, blank=True)
    share_token = models.CharField("Shaxsiy havola kaliti", max_length=64, blank=True, editable=False)
    music = models.FileField("Musiqa fayli (mp3)", upload_to="music/", blank=True, null=True,
                             help_text="Muzeyga kirganda sekin ijro etiladi. Mp3 tavsiya etiladi.")
    letter_title = models.CharField("Xat sarlavhasi", max_length=120, blank=True, default="Sevgilimga xat")
    letter_text = models.TextField("Xat matni", blank=True,
                                   help_text="Yoʻlakning oxirgi devorida katta lavha boʻlib turadi. Bosilsa, xat ochiladi.")
    together_since = models.DateField("Birga boʻlgan sana", null=True, blank=True,
                                      help_text="Lavhada “Biz birga ... kun” deb hisoblab turadi.")
    video = models.FileField("Xat oldidagi video", upload_to="video/", blank=True, null=True,
                             help_text="Oxirgi xonada, xat yonida kichik ekranda jiringlaydi. Qisqa mp4 tavsiya etiladi.")
    letter_pos = models.PositiveIntegerField(
        "Xat lavhasi oʻrni", default=0,
        help_text="Xat lavhasi nechanchi devor ramkasi oʻrnida turadi (boshidan sanaladi). 0 — eng oxirida. Xaritada L belgisi qoʻyilgan boʻlsa, oʻsha ustun.")
    video_pos = models.PositiveIntegerField(
        "Video oʻrni", default=0,
        help_text="Video nechanchi devor ramkasi oʻrnida turadi. 0 — xatdan oldingi joyda. Xaritada V belgisi qoʻyilgan boʻlsa, oʻsha ustun.")
    map_data = models.TextField("Qoʻlda chizilgan xarita", blank=True, editable=False)

    class Meta:
        verbose_name = "Muzey sozlamalari"
        verbose_name_plural = "Muzey sozlamalari"

    def save(self, *a, **kw):
        self.pk = 1
        super().save(*a, **kw)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return self.title


class Photo(models.Model):
    title = models.CharField("Izoh", max_length=120, blank=True)
    image = models.ImageField("Rasm", upload_to="photos/")
    order = models.PositiveIntegerField("Tartib", default=0, help_text="Kichik raqam — avval koʻrinadi.")
    date = models.DateField("Sana", null=True, blank=True)
    story = models.TextField("Hikoya", blank=True, help_text="Rasm ochilganda izoh tagida chiroyli chiqadi.")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Rasm"
        verbose_name_plural = "Rasmlar"

    def save(self, *a, **kw):
        f = self.image
        if f and not getattr(f, "_committed", True):  # yangi yuklangan: kichraytirish
            img = ImageOps.exif_transpose(Image.open(f))
            img.thumbnail((1800, 1800))
            buf = BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=86)
            name = os.path.splitext(os.path.basename(f.name))[0] + ".jpg"
            self.image.save(name, ContentFile(buf.getvalue()), save=False)
        super().save(*a, **kw)

    def __str__(self):
        return self.title or f"Rasm {self.pk}"


class DailyVisit(models.Model):
    date = models.DateField(unique=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Kunlik tashrif"
        verbose_name_plural = "Kunlik tashriflar"


class GuestEntry(models.Model):
    photo = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL)
    text = models.CharField("Xabar", max_length=300, blank=True)
    is_heart = models.BooleanField("Yurakcha", default=False)
    seen = models.BooleanField("Oʻqildi", default=False)
    created = models.DateTimeField("Vaqti", auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Mehmon xabari"
        verbose_name_plural = "Mehmonlar daftari"
