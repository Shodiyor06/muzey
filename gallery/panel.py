"""Maxsus boshqaruv paneli — Django adminning standart koʻrinishi oʻrniga."""
import secrets
from datetime import timedelta
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince

from .layouts import MAPS, PALETTE_HEX, map_meters, museum_map, slots
from .models import DailyVisit, GuestEntry, Photo, SiteSettings

def member(view):
    """Faqat kirgan foydalanuvchi (Telegram bot havolasi orqali) oʻz panelini koʻradi."""
    @wraps(view)
    def wrapper(request, *a, **kw):
        u = request.user
        if not u.is_authenticated:
            return redirect("/")
        tg = getattr(u, "tg", None)
        if tg is not None and tg.blocked:
            logout(request)
            return redirect("/")
        return view(request, *a, **kw)
    return wrapper


def mine(request):
    """Foydalanuvchining oʻz muzeyi sozlamalari."""
    return SiteSettings.for_user(request.user)


def ctx(s, page, **extra):
    return {"museum": s, "page": page, "CELL": 4,
            "unseen": GuestEntry.objects.filter(owner=s.owner, seen=False).count(), **extra}


class MultiFile(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultiFileField, self).clean(f, initial) for f in files if f]


class UploadForm(forms.Form):
    images = MultiFileField(
        label="Rasmlar",
        widget=MultiFile(attrs={"multiple": True, "accept": "image/*"}),
    )


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ("title", "date", "story", "order", "image")
        widgets = {"story": forms.Textarea(attrs={"rows": 4})}


class SettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ("title", "subtitle", "layout", "palette", "music",
                  "letter_title", "letter_text", "together_since", "video",
                  "letter_pos", "video_pos")


def photo_capacity(s, n, m=None):
    """Ramkalar soni (xat va video uchun joy ayirilgan)."""
    m = m or museum_map(s, n, bool(s.video))
    return max(0, len(slots(m)) - 1 - (1 if s.video else 0))


@member
def dashboard(request):
    s = mine(request)
    me = request.user
    photos = Photo.objects.filter(owner=me).annotate(
        _h=Count("guestentry", filter=Q(guestentry__is_heart=True)),
        _c=Count("guestentry", filter=~Q(guestentry__text="")))
    n = photos.count()
    m = museum_map(s, n, bool(s.video))
    cap = photo_capacity(s, n, m)
    today = timezone.localdate()
    days = [today - timedelta(d) for d in range(6, -1, -1)]
    counts = {v.date: v.count for v in DailyVisit.objects.filter(owner=me, date__gte=days[0])}
    vals = [counts.get(d, 0) for d in days]
    mx = max(vals) or 1
    total = DailyVisit.objects.filter(owner=me).aggregate(t=Sum("count"))["t"] or 0
    steps = [
        ("Rasmlarni yuklang", "Bir necha rasmni birdan yuklash mumkin.",
         n > 0, reverse("panel_upload")),
        ("Rasmlarga sana va hikoya yozing", "Rasm ochilganda izoh tagida chiqadi.",
         Photo.objects.filter(owner=me).exclude(story="").exists(), reverse("panel_photos")),
        ("Shaxsiy havola yarating", "Sevgilingiz parolsiz kirishi uchun bir havola.",
         bool(s.share_token), reverse("panel_settings")),
        ("Fon musiqasini yuklang", "Mp3 fayl, kirganda sekin ijro etiladi.",
         bool(s.music), reverse("panel_settings")),
        ("Oxirgi xonaga video qoʻying", "Xat oldidagi kichik ekranda chiqadi.",
         bool(s.video), reverse("panel_settings")),
        ("Soʻnggi xona xatini yozing", "Yoʻlak oxiridagi katta lavha.",
         bool(s.letter_text), reverse("panel_settings")),
        ("Birga boʻlgan sanani kiriting", "“Biz birga ... kun” hisoblagichi uchun.",
         bool(s.together_since), reverse("panel_settings")),
    ]
    entries = GuestEntry.objects.filter(owner=me).select_related("photo")[:6]
    return render(request, "panel/dashboard.html", ctx(s, "home", dash={
        "photos": n, "cap": cap, "fill": min(100, round(n / cap * 100)) if cap else 0,
        "over": max(0, n - cap), "custom_map": bool((s.map_data or "").strip()),
        "layout": s.get_layout_display(), "palette": s.get_palette_display(),
        "color": PALETTE_HEX.get(s.palette, "#7a3f56"), "title": s.title,
        "meters": map_meters(m), "map": m,
        "today": vals[-1], "week": sum(vals), "total": total,
        "chart": [{"label": d.strftime("%d.%m"), "n": v, "h": max(4, round(v / mx * 100)) if v else 4}
                  for d, v in zip(days, vals)],
        "recent": photos.order_by("-created")[:8],
        "share": bool(s.share_token),
        "url": request.build_absolute_uri(reverse("share_entry", args=[s.share_token])) if s.share_token else "",
        "video": bool(s.video),
        "steps": [{"label": a, "hint": b, "done": c, "url": d} for a, b, c, d in steps],
        "progress": round(sum(1 for x in steps if x[2]) / len(steps) * 100),
        "hearts": GuestEntry.objects.filter(owner=me, is_heart=True).count(),
        "comments": GuestEntry.objects.filter(owner=me).exclude(text="").count(),
        "unseen": GuestEntry.objects.filter(owner=me, seen=False).count(),
        "entries": [{"text": e.text, "heart": e.is_heart, "photo": e.photo.title if e.photo else "",
                     "age": timesince(e.created).split(",")[0], "new": not e.seen} for e in entries],
    }))


@member
def photos(request):
    s = mine(request)
    form = UploadForm()
    photos_qs = Photo.objects.filter(owner=request.user).annotate(
        hearts_n=Count("guestentry", filter=Q(guestentry__is_heart=True)))
    return render(request, "panel/photos.html", ctx(
        s, "photos", form=form, photos=photos_qs, cap=photo_capacity(s, Photo.objects.filter(owner=request.user).count())))


@member
def upload(request):
    s = mine(request)
    if request.method != "POST":
        return redirect("panel_photos")
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Rasmlar tanlanmadi.")
        return redirect("panel_photos")
    start = Photo.objects.filter(owner=request.user).count()
    files = form.cleaned_data["images"]
    for i, f in enumerate(files):
        Photo.objects.create(owner=request.user, image=f, title=f.name.rsplit(".", 1)[0], order=start + i)
    messages.success(request, f"{len(files)} ta rasm yuklandi. Endi har biriga sana va hikoya yozing.")
    return redirect("panel_photos")


@member
def photo_edit(request, pk):
    s = mine(request)
    photo = get_object_or_404(Photo, pk=pk, owner=request.user)
    if request.method == "POST":
        form = PhotoForm(request.POST, request.FILES, instance=photo)
        if form.is_valid():
            form.save()
            messages.success(request, "Rasm saqlandi.")
            return redirect("panel_photos")
    else:
        form = PhotoForm(instance=photo)
    return render(request, "panel/photo_edit.html", ctx(s, "photos", form=form, photo=photo))


@member
def photo_delete(request, pk):
    if request.method != "POST":
        return redirect("panel_photos")
    photo = get_object_or_404(Photo, pk=pk, owner=request.user)
    photo.delete()
    messages.success(request, "Rasm oʻchirildi.")
    return redirect("panel_photos")


@member
def settings_view(request):
    s = mine(request)
    if request.method == "POST":
        form = SettingsForm(request.POST, request.FILES, instance=s)
        if form.is_valid():
            form.save()
            messages.success(request, "Sozlamalar saqlandi. Muzey yangilandi.")
            return redirect("panel_settings")
        messages.error(request, "Baʼzi maydonlarda xato bor.")
    else:
        form = SettingsForm(instance=s)
    m = museum_map(s, Photo.objects.filter(owner=request.user).count(), bool(s.video))
    share_url = (request.build_absolute_uri(reverse("share_entry", args=[s.share_token]))
                 if s.share_token else "")
    return render(request, "panel/settings.html", ctx(
        s, "settings", form=form, cap=photo_capacity(s, Photo.objects.filter(owner=request.user).count(), m), meters=map_meters(m),
        share_url=share_url))


@member
def share_action(request):
    if request.method != "POST":
        return redirect("panel_settings")
    s = mine(request)
    action = request.POST.get("action")
    if action == "off":
        SiteSettings.objects.filter(pk=s.pk).update(share_token="")
        messages.success(request, "Shaxsiy havola oʻchirildi. Endi muzeyga faqat siz kira olasiz.")
    elif action == "new":
        SiteSettings.objects.filter(pk=s.pk).update(share_token=secrets.token_urlsafe(24))
        messages.success(request, "Yangi shaxsiy havola yaratildi. Uni sevgilingizga yuboring.")
    return redirect("panel_settings")


@member
def map_editor(request):
    s = mine(request)
    n = Photo.objects.filter(owner=request.user).count()
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "auto":
            SiteSettings.objects.filter(pk=s.pk).update(map_data="")
            messages.success(request, "Qoʻlda chizilgan xarita oʻchirildi. Muzey endi rasmlar soniga moslashadi.")
        else:
            from .layouts import parse
            m = parse(request.POST.get("map", ""))
            if not m:
                messages.error(request, "Xarita notoʻgʻri: boshlanish nuqtasi (S) va ulanadigan pol boʻlishi shart.")
            else:
                SiteSettings.objects.filter(pk=s.pk).update(map_data="\n".join(m))
                messages.success(request, "Xarita saqlandi.")
        return redirect("panel_map")
    m = museum_map(s, n, bool(s.video))
    return render(request, "panel/map.html", ctx(
        s, "map", presets=MAPS, current=m,
        cap=photo_capacity(s, n, m), reserved=1 + (1 if s.video else 0),
        photos=n, custom=bool((s.map_data or "").strip())))


@member
def guests(request):
    s = mine(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "seen":
            GuestEntry.objects.filter(owner=request.user, seen=False).update(seen=True)
            messages.success(request, "Hamma xabar oʻqildi deb belgilandi.")
        elif action == "delete":
            GuestEntry.objects.filter(owner=request.user, pk=request.POST.get("pk")).delete()
            messages.success(request, "Xabar oʻchirildi.")
        return redirect("panel_guests")
    return render(request, "panel/guests.html", ctx(
        s, "guests", entries=GuestEntry.objects.filter(owner=request.user).select_related("photo"),
        unseen=GuestEntry.objects.filter(owner=request.user, seen=False).count()))
