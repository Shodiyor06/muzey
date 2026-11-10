from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from .models import GuestEntry, Photo, SiteSettings

admin.site.site_header = "Muzey boshqaruvi"
admin.site.site_title = "Muzey"
admin.site.index_title = "Bosh sahifa"


class SettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        exclude = ("map_data", "telegram_token", "share_token")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    form = SettingsForm
    readonly_fields = ()
    fieldsets = [
        ("1. Asosiy matnlar", {"fields": ("title", "subtitle"),
                               "description": "Kirish ekranida koʻrinadigan sarlavha va qisqa xat."}),
        ("2. Zal koʻrinishi", {"fields": ("layout", "palette"),
                               "description": "Zal shakli va devor rangi. Rasmlar koʻp boʻlsa, kattaroq zal tanlang."}),
        ("3. Kirish", {"fields": ("telegram_bot", "telegram_id"),
                       "description": "Muzeyga faqat shu Telegram akkaunt egasi kira oladi. Bot tokeni va havola asosiy panelda boshqariladi."}),
        ("4. Fon musiqasi", {"fields": ("music",)}),
        ("5. Soʻnggi xona (xat va video)", {"fields": ("letter_title", "letter_text", "together_since", "video", "letter_pos", "video_pos"),
                                           "description": "Xat va video oxirgi xonada chiqadi. Video xat yonidagi kichik ekranda jiringlaydi."}),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:gallery_sitesettings_change", args=[SiteSettings.load().pk]))

    def response_change(self, request, obj):
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("admin:index")


class MultiFile(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultiFileField, self).clean(f, initial) for f in files if f]


class BulkForm(forms.Form):
    images = MultiFileField(label="Rasmlar", widget=MultiFile(attrs={"multiple": True, "accept": "image/*"}))


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("thumb", "title", "date", "order", "hearts", "comments")
    list_display_links = ("thumb",)
    list_editable = ("title", "order")
    fields = ("title", "date", "story", "image", "order", "thumb")
    readonly_fields = ("thumb",)
    change_list_template = "admin/gallery/photo/change_list.html"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _h=Count("guestentry", filter=Q(guestentry__is_heart=True)),
            _c=Count("guestentry", filter=~Q(guestentry__text="")))

    @admin.display(description="Rasm")
    def thumb(self, o):
        return format_html('<img src="{}" style="height:64px;border-radius:6px">', o.image.url) if o.image else "-"

    @admin.display(description="♥", ordering="_h")
    def hearts(self, o):
        return o._h

    @admin.display(description="Izohlar", ordering="_c")
    def comments(self, o):
        return o._c

    def get_urls(self):
        return [path("bulk/", self.admin_site.admin_view(self.bulk), name="gallery_photo_bulk")] + super().get_urls()

    def bulk(self, request):
        form = BulkForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            start = Photo.objects.count()
            for i, f in enumerate(form.cleaned_data["images"]):
                Photo.objects.create(image=f, title=f.name.rsplit(".", 1)[0], order=start + i)
            messages.success(request, "Rasmlar yuklandi. Endi har biriga sana va hikoya yozishingiz mumkin.")
            return redirect("admin:gallery_photo_changelist")
        ctx = {**self.admin_site.each_context(request), "form": form, "title": "Koʻp rasm yuklash"}
        return render(request, "admin/gallery/photo/bulk.html", ctx)


@admin.register(GuestEntry)
class GuestEntryAdmin(admin.ModelAdmin):
    list_display = ("kind", "text", "photo", "created", "seen")
    list_filter = ("seen", "is_heart")
    actions = ["mark_seen"]

    @admin.display(description="Turi")
    def kind(self, o):
        return "♥ Yurakcha" if o.is_heart and not o.text else "Izoh"

    def has_add_permission(self, request):
        return False

    @admin.action(description="Oʻqildi deb belgilash")
    def mark_seen(self, request, qs):
        qs.update(seen=True)
