import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from access import tg
from access.models import AccessToken, TgVisitor
from gallery.models import Photo, SiteSettings

User = get_user_model()
TMP = tempfile.mkdtemp()


def png():
    b = io.BytesIO()
    Image.new("RGB", (40, 30), "pink").save(b, "PNG")
    return SimpleUploadedFile("a.png", b.getvalue(), "image/png")


@override_settings(MEDIA_ROOT=TMP)
class MultiUserFlow(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def bot(self, tg_id, data="enter", name="Ali"):
        """Botga callback yuboradi; botning javob xabarini qaytaradi."""
        with mock.patch.object(tg, "api") as api:
            tg.handle({"callback_query": {"id": "1", "data": data,
                                           "from": {"id": tg_id, "first_name": name}}}, "https://muzey.test/")
        return [c for c in api.call_args_list if c.args[0] == "sendMessage"][-1].kwargs

    def link_of(self, msg):
        return msg["reply_markup"]["inline_keyboard"][0][0]["url"]

    def test_site_has_no_registration_login_page_only(self):
        r = Client().get("/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Telegram")
        self.assertNotContains(r, "<form")
        self.assertEqual(Client().get("/api/config/").status_code, 403)
        self.assertEqual(Client().get("/admin/").status_code, 302)  # panel: login sahifasiga

    def test_bot_registers_and_gives_permanent_login_link(self):
        msg = self.bot(111)
        v = TgVisitor.objects.get(tg_id=111)
        self.assertEqual(v.user.username, "tg111")
        self.assertFalse(v.user.is_staff)
        tok = AccessToken.objects.get(visitor=v)
        self.assertIsNone(tok.expires_at)  # 2 kunlik emas, muddatsiz
        self.assertIn(f"/enter/{tok.key}/", self.link_of(msg))
        # qayta bosilsa, yangi foydalanuvchi/kalit yaratilmaydi
        self.bot(111)
        self.assertEqual(User.objects.filter(username="tg111").count(), 1)
        self.assertEqual(AccessToken.objects.filter(visitor=v).count(), 1)

    def test_link_logs_into_own_profile(self):
        key = self.link_of(self.bot(111)).split("/enter/")[1].strip("/")
        c = Client()
        r = c.get(f"/enter/{key}/")
        self.assertRedirects(r, "/admin/")
        self.assertEqual(c.get("/admin/").status_code, 200)
        self.assertEqual(c.get("/").status_code, 200)  # oʻz muzeyi
        self.assertEqual(c.get("/api/config/").status_code, 200)
        self.assertEqual(Client().get("/enter/xato/").status_code, 410)

    def test_renew_revokes_old_link(self):
        old = self.link_of(self.bot(111)).split("/enter/")[1].strip("/")
        new = self.link_of(self.bot(111, "renew")).split("/enter/")[1].strip("/")
        self.assertNotEqual(old, new)
        self.assertEqual(Client().get(f"/enter/{old}/").status_code, 410)
        self.assertEqual(Client().get(f"/enter/{new}/").status_code, 302)

    def login(self, tg_id, name="Ali"):
        c = Client()
        c.get("/enter/" + self.link_of(self.bot(tg_id, name=name)).split("/enter/")[1])
        return c

    def test_users_are_isolated_and_share_link_works(self):
        a, b = self.login(1, "Ali"), self.login(2, "Vali")
        a.post("/admin/rasmlar/yuklash/", {"images": png()})
        ua, ub = User.objects.get(username="tg1"), User.objects.get(username="tg2")
        self.assertEqual(Photo.objects.filter(owner=ua).count(), 1)
        self.assertEqual(Photo.objects.filter(owner=ub).count(), 0)
        self.assertEqual(len(b.get("/api/config/").json()["photos"]), 0)
        url = a.get("/api/config/").json()["photos"][0]["src"]
        self.assertEqual(a.get(url).status_code, 200)
        self.assertEqual(b.get(url).status_code, 404)           # boshqa foydalanuvchi rasmi berilmaydi
        self.assertEqual(Client().get(url).status_code, 404)
        pid = Photo.objects.get(owner=ua).pk
        self.assertEqual(b.get(f"/admin/rasmlar/{pid}/").status_code, 404)
        self.assertEqual(b.post(f"/admin/rasmlar/{pid}/ochirish/").status_code, 404)

        # A sevgilisi uchun havola yaratadi
        a.post("/admin/sozlamalar/havola/", {"action": "new"})
        token = SiteSettings.objects.get(owner=ua).share_token
        self.assertTrue(token)
        g = Client()
        self.assertEqual(g.get("/api/config/").status_code, 403)
        self.assertEqual(g.get(f"/kirish/{token}/").status_code, 302)
        self.assertEqual(len(g.get("/api/config/").json()["photos"]), 1)
        self.assertEqual(g.get(url).status_code, 200)
        self.assertEqual(g.get("/admin/").status_code, 302)      # mehmon panelga kira olmaydi
        g.post("/api/guest/", data='{"heart": true, "photo": %d}' % pid, content_type="application/json")
        self.assertEqual(ua.guest_entries.count(), 1)
        self.assertEqual(ub.guest_entries.count(), 0)
        self.assertEqual(Client().get("/kirish/notoqri/").status_code, 404)

        # roʻyxatdan oʻtgan mehmon ham yuborilgan muzeyni koʻradi, /ozim/ — oʻziga qaytadi
        b.get(f"/kirish/{token}/")
        self.assertEqual(len(b.get("/api/config/").json()["photos"]), 1)
        b.get("/ozim/")
        self.assertEqual(len(b.get("/api/config/").json()["photos"]), 0)

        # havola oʻchirilsa, mehmon kira olmaydi
        a.post("/admin/sozlamalar/havola/", {"action": "off"})
        self.assertEqual(g.get("/api/config/").status_code, 403)

    def test_blocked_user_cannot_enter(self):
        key = self.link_of(self.bot(5)).split("/enter/")[1].strip("/")
        TgVisitor.objects.filter(tg_id=5).update(blocked=True)
        self.assertEqual(Client().get(f"/enter/{key}/").status_code, 410)

    def test_owner_gets_legacy_museum(self):
        admin = User.objects.create_superuser("admin", "a@a.a", "pw")
        old = SiteSettings.objects.create(title="Eski muzey")
        Photo.objects.create(image=png(), title="eski")
        with mock.patch.dict("os.environ", {"TELEGRAM_OWNER_IDS": "9"}):
            c = Client()
            c.get("/enter/" + self.link_of(self.bot(9, name="Egasi")).split("/enter/")[1])
        self.assertEqual(TgVisitor.objects.get(tg_id=9).user, admin)
        self.assertEqual(c.get("/admin/").status_code, 200)  # birinchi kirishda eski muzey egasiga biriktiriladi
        old.refresh_from_db()
        self.assertEqual(old.owner, admin)
        self.assertEqual(Photo.objects.get(title="eski").owner, admin)
        self.assertEqual(len(c.get("/api/config/").json()["photos"]), 1)

    def test_letter_and_video_position_in_config(self):
        c = self.login(7)
        c.post("/admin/xarita/", {"action": "save", "map": "#######\n#S..L.#\n#.###.#\n#V....#\n#######"})
        c.post("/admin/sozlamalar/", {"title": "T", "subtitle": "s", "layout": "winding", "palette": "rose",
                                      "letter_title": "x", "letter_text": "y", "letter_pos": 3, "video_pos": 4})
        cfg = c.get("/api/config/").json()
        self.assertEqual((cfg["letter"]["pos"], cfg["video_pos"]), (3, 4))
        self.assertIn("L", "".join(cfg["map"]))
