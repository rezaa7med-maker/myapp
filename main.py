# main.py
import os, json, time, threading, ssl, traceback
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivy.config import Config
from kivy.resources import resource_find

# --- گرافیک: مطمئن شو فول‌اسکرین خاموشه
Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "resizable", "1")

from kivy.core.window import Window
Window.fullscreen = False

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.graphics import Color, Rectangle

import requests
import feedparser
import certifi

# -----------------------------
CONFIG_PATH = "config.json"

# ✅ فونت صفر ریسک:
# اگر فونت نبود، None میشه و Kivy میره روی فونت پیش‌فرض
FONT_CANDIDATES = [
    "assets/fonts/Vazirmatn-Regular.ttf",
    "assets/fonts/vazirmatn-regular.ttf",
    "Vazirmatn-Regular.ttf",
]
APP_FONT = None
for p in FONT_CANDIDATES:
    fp = resource_find(p) or (p if os.path.exists(p) else None)
    if fp:
        APP_FONT = fp
        break

def fkw():
    """font kwargs -> همیشه امن"""
    return {"font_name": APP_FONT} if APP_FONT else {}

# -----------------------------
DEFAULT_SENDERS = [
    {"email": "example@gmail.com", "app_password": "xxxx xxxx xxxx xxxx"}
]
DEFAULT_RECIPIENTS = [
    {"email": "friend1@gmail.com", "enabled": True},
    {"email": "friend2@gmail.com", "enabled": False},
]
DEFAULT_FEEDS = [
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.theguardian.com/world/rss",
]

# -----------------------------
def safe_load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def safe_save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# -----------------------------
class NewsApp(App):
    def build(self):
        self.title = "News Mailer"
        self.senders = []
        self.recipients = []
        self.feeds = []
        self._loading = False

        self._load_config()

        # --- روت اصلی
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
        self.root = root

        # --- پس‌زمینه نرم و تیره
        with root.canvas.before:
            Color(0.08, 0.08, 0.08, 1)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)

        # ----- بالا: مدیریت حساب‌ها
        top = GridLayout(cols=2, spacing=dp(10), size_hint=(1, None))
        top.bind(minimum_height=top.setter("height"))

        # Senders box
        senders_box = BoxLayout(orientation="vertical", spacing=dp(6))
        senders_title = Label(
            text="Sender Accounts",
            font_size="16sp",
            size_hint=(1, None),
            height=dp(26),
            halign="left",
            valign="middle",
            color=(1,1,1,1),
            **fkw()
        )
        senders_title.bind(size=senders_title.setter("text_size"))

        self.senders_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.senders_list.bind(minimum_height=self.senders_list.setter("height"))
        senders_scroll = ScrollView(size_hint=(1, None), height=dp(160))
        senders_scroll.add_widget(self.senders_list)

        senders_buttons = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_add_sender = Button(text="Add Sender", **fkw())
        btn_add_sender.bind(on_release=self._popup_add_sender)
        btn_del_sender = Button(text="Delete Sender", **fkw())
        btn_del_sender.bind(on_release=self._popup_delete_sender)
        senders_buttons.add_widget(btn_add_sender)
        senders_buttons.add_widget(btn_del_sender)

        senders_box.add_widget(senders_title)
        senders_box.add_widget(senders_scroll)
        senders_box.add_widget(senders_buttons)

        # Recipients box
        recipients_box = BoxLayout(orientation="vertical", spacing=dp(6))
        recipients_title = Label(
            text="Recipients",
            font_size="16sp",
            size_hint=(1, None),
            height=dp(26),
            halign="left",
            valign="middle",
            color=(1,1,1,1),
            **fkw()
        )
        recipients_title.bind(size=recipients_title.setter("text_size"))

        self.recipients_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.recipients_list.bind(minimum_height=self.recipients_list.setter("height"))
        recipients_scroll = ScrollView(size_hint=(1, None), height=dp(160))
        recipients_scroll.add_widget(self.recipients_list)

        recipients_buttons = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_add_rec = Button(text="Add Recipient", **fkw())
        btn_add_rec.bind(on_release=self._popup_add_recipient)
        btn_del_rec = Button(text="Delete Recipient", **fkw())
        btn_del_rec.bind(on_release=self._popup_delete_recipient)
        recipients_buttons.add_widget(btn_add_rec)
        recipients_buttons.add_widget(btn_del_rec)

        recipients_box.add_widget(recipients_title)
        recipients_box.add_widget(recipients_scroll)
        recipients_box.add_widget(recipients_buttons)

        top.add_widget(senders_box)
        top.add_widget(recipients_box)

        # ----- وسط: Feeds
        feeds_box = BoxLayout(orientation="vertical", spacing=dp(6),
                              size_hint=(1, None), height=dp(170))
        feeds_title = Label(
            text="RSS Feeds",
            font_size="16sp",
            size_hint=(1, None),
            height=dp(26),
            halign="left",
            valign="middle",
            color=(1,1,1,1),
            **fkw()
        )
        feeds_title.bind(size=feeds_title.setter("text_size"))

        self.feeds_list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.feeds_list.bind(minimum_height=self.feeds_list.setter("height"))
        feeds_scroll = ScrollView(size_hint=(1, None), height=dp(100))
        feeds_scroll.add_widget(self.feeds_list)

        feeds_buttons = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_add_feed = Button(text="Add Feed", **fkw())
        btn_add_feed.bind(on_release=self._popup_add_feed)
        btn_del_feed = Button(text="Delete Feed", **fkw())
        btn_del_feed.bind(on_release=self._popup_delete_feed)
        feeds_buttons.add_widget(btn_add_feed)
        feeds_buttons.add_widget(btn_del_feed)

        feeds_box.add_widget(feeds_title)
        feeds_box.add_widget(feeds_scroll)
        feeds_box.add_widget(feeds_buttons)

        # ----- پایین: actions + output
        actions = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(8))
        self.spinner_lang = Spinner(
            text="English",
            values=("English", "Persian"),
            size_hint=(None, 1),
            width=dp(140),
            **fkw()
        )
        btn_collect = Button(text="Collect News", **fkw())
        btn_collect.bind(on_release=self.collect_news_safe)
        btn_send = Button(text="Send Emails", **fkw())
        btn_send.bind(on_release=self.send_emails_safe)

        actions.add_widget(self.spinner_lang)
        actions.add_widget(btn_collect)
        actions.add_widget(btn_send)

        self.status_label = Label(
            text="Ready...",
            font_size="16sp",
            size_hint=(1, None),
            height=dp(220),
            halign="right",
            valign="top",
            color=(1,1,1,1),
            **fkw()
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        status_scroll = ScrollView()
        status_scroll.add_widget(self.status_label)

        # add to root
        root.add_widget(top)
        root.add_widget(feeds_box)
        root.add_widget(actions)
        root.add_widget(status_scroll)

        self.refresh_senders_list()
        self.refresh_recipients_list()
        self.refresh_feeds_list()

        return root

    # -----------------------------
    def _update_bg(self, *_):
        self._bg_rect.pos = self.root.pos
        self._bg_rect.size = self.root.size

    # -----------------------------
    def on_start(self):
        Window.fullscreen = False
        Clock.schedule_once(self._apply_system_ui, 0)
        Clock.schedule_once(self._apply_system_ui, 0.5)
        Clock.schedule_once(self._apply_system_ui, 1.0)

    def _apply_system_ui(self, *_):
        if platform != "android":
            return
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass

            @run_on_ui_thread
            def _do():
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                LayoutParams = autoclass("android.view.WindowManager$LayoutParams")
                View = autoclass("android.view.View")

                activity = PythonActivity.mActivity
                window = activity.getWindow()
                decor = window.getDecorView()

                window.clearFlags(LayoutParams.FLAG_FULLSCREEN)
                window.clearFlags(LayoutParams.FLAG_TRANSLUCENT_STATUS)
                window.clearFlags(LayoutParams.FLAG_TRANSLUCENT_NAVIGATION)
                window.addFlags(LayoutParams.FLAG_FORCE_NOT_FULLSCREEN)
                decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE)

            _do()
        except Exception:
            pass

    # -----------------------------
    def _load_config(self):
        data = safe_load_json(CONFIG_PATH, {})
        self.senders = data.get("senders", DEFAULT_SENDERS.copy())
        self.recipients = data.get("recipients", DEFAULT_RECIPIENTS.copy())
        self.feeds = data.get("feeds", DEFAULT_FEEDS.copy())

    def _save_config(self):
        data = {
            "senders": self.senders,
            "recipients": self.recipients,
            "feeds": self.feeds,
        }
        safe_save_json(CONFIG_PATH, data)

    # -----------------------------
    def refresh_senders_list(self):
        self.senders_list.clear_widgets()
        for i, s in enumerate(self.senders):
            row = BoxLayout(size_hint_y=None, height=dp(32))
            lbl = Label(
                text=f"[{i+1}] {s.get('email','')}",
                font_size="14sp",
                halign="left",
                valign="middle",
                color=(0.9,0.9,0.9,1),
                **fkw()
            )
            lbl.bind(size=lbl.setter("text_size"))
            row.add_widget(lbl)
            self.senders_list.add_widget(row)

    def refresh_recipients_list(self):
        self.recipients_list.clear_widgets()
        for i, r in enumerate(self.recipients):
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
            cb = CheckBox(active=r.get("enabled", True))
            cb.bind(active=lambda inst, val, idx=i: self._toggle_recipient(idx, val))
            lbl = Label(
                text=f"[{i+1}] {r.get('email','')}",
                font_size="14sp",
                halign="left",
                valign="middle",
                color=(0.9,0.9,0.9,1),
                **fkw()
            )
            lbl.bind(size=lbl.setter("text_size"))
            row.add_widget(cb)
            row.add_widget(lbl)
            self.recipients_list.add_widget(row)

    def refresh_feeds_list(self):
        self.feeds_list.clear_widgets()
        for i, url in enumerate(self.feeds):
            row = BoxLayout(size_hint_y=None, height=dp(30))
            lbl = Label(
                text=f"[{i+1}] {url}",
                font_size="13sp",
                halign="left",
                valign="middle",
                color=(0.85,0.85,0.85,1),
                **fkw()
            )
            lbl.bind(size=lbl.setter("text_size"))
            row.add_widget(lbl)
            self.feeds_list.add_widget(row)

    def _toggle_recipient(self, idx, val):
        if 0 <= idx < len(self.recipients):
            self.recipients[idx]["enabled"] = bool(val)
            self._save_config()

    # -----------------------------
    # Popups for add/delete
    def _popup_add_sender(self, *_):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_email = TextInput(hint_text="Gmail address", multiline=False, **fkw())
        ti_pass = TextInput(hint_text="App password", multiline=False, password=True, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Add", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_email)
        content.add_widget(ti_pass)
        content.add_widget(btns)

        pop = Popup(title="Add Sender", content=content, size_hint=(0.9, 0.6))
        btn_cancel.bind(on_release=pop.dismiss)

        def _add(*_):
            email = ti_email.text.strip()
            app_pass = ti_pass.text.strip()
            if email and app_pass:
                self.senders.append({"email": email, "app_password": app_pass})
                self._save_config()
                self.refresh_senders_list()
                pop.dismiss()
        btn_ok.bind(on_release=_add)

        pop.open()

    def _popup_delete_sender(self, *_):
        if not self.senders:
            self._toast("No senders to delete.")
            return

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_idx = TextInput(hint_text="Sender number to delete (e.g. 1)", multiline=False, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Delete", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_idx)
        content.add_widget(btns)

        pop = Popup(title="Delete Sender", content=content, size_hint=(0.9, 0.5))
        btn_cancel.bind(on_release=pop.dismiss)

        def _del(*_):
            try:
                idx = int(ti_idx.text.strip()) - 1
                if 0 <= idx < len(self.senders):
                    self.senders.pop(idx)
                    self._save_config()
                    self.refresh_senders_list()
                    pop.dismiss()
            except:
                pass

        btn_ok.bind(on_release=_del)
        pop.open()

    def _popup_add_recipient(self, *_):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_email = TextInput(hint_text="Recipient email", multiline=False, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Add", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_email)
        content.add_widget(btns)

        pop = Popup(title="Add Recipient", content=content, size_hint=(0.9, 0.5))
        btn_cancel.bind(on_release=pop.dismiss)

        def _add(*_):
            email = ti_email.text.strip()
            if email:
                self.recipients.append({"email": email, "enabled": True})
                self._save_config()
                self.refresh_recipients_list()
                pop.dismiss()

        btn_ok.bind(on_release=_add)
        pop.open()

    def _popup_delete_recipient(self, *_):
        if not self.recipients:
            self._toast("No recipients to delete.")
            return

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_idx = TextInput(hint_text="Recipient number to delete (e.g. 1)", multiline=False, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Delete", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_idx)
        content.add_widget(btns)

        pop = Popup(title="Delete Recipient", content=content, size_hint=(0.9, 0.5))
        btn_cancel.bind(on_release=pop.dismiss)

        def _del(*_):
            try:
                idx = int(ti_idx.text.strip()) - 1
                if 0 <= idx < len(self.recipients):
                    self.recipients.pop(idx)
                    self._save_config()
                    self.refresh_recipients_list()
                    pop.dismiss()
            except:
                pass

        btn_ok.bind(on_release=_del)
        pop.open()

    def _popup_add_feed(self, *_):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_url = TextInput(hint_text="RSS feed URL", multiline=False, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Add", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_url)
        content.add_widget(btns)

        pop = Popup(title="Add Feed", content=content, size_hint=(0.9, 0.5))
        btn_cancel.bind(on_release=pop.dismiss)

        def _add(*_):
            url = ti_url.text.strip()
            if url:
                self.feeds.append(url)
                self._save_config()
                self.refresh_feeds_list()
                pop.dismiss()

        btn_ok.bind(on_release=_add)
        pop.open()

    def _popup_delete_feed(self, *_):
        if not self.feeds:
            self._toast("No feeds to delete.")
            return

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        ti_idx = TextInput(hint_text="Feed number to delete (e.g. 1)", multiline=False, **fkw())

        btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(6))
        btn_ok = Button(text="Delete", **fkw())
        btn_cancel = Button(text="Cancel", **fkw())
        btns.add_widget(btn_ok); btns.add_widget(btn_cancel)

        content.add_widget(ti_idx)
        content.add_widget(btns)

        pop = Popup(title="Delete Feed", content=content, size_hint=(0.9, 0.5))
        btn_cancel.bind(on_release=pop.dismiss)

        def _del(*_):
            try:
                idx = int(ti_idx.text.strip()) - 1
                if 0 <= idx < len(self.feeds):
                    self.feeds.pop(idx)
                    self._save_config()
                    self.refresh_feeds_list()
                    pop.dismiss()
            except:
                pass

        btn_ok.bind(on_release=_del)
        pop.open()

    # -----------------------------
    def _toast(self, msg):
        self.status_label.text = msg

    def _append_status(self, msg):
        self.status_label.text += f"\n{msg}"

    # -----------------------------
    def collect_news_safe(self, *_):
        if self._loading:
            return
        self._loading = True
        self.status_label.text = "Collecting news..."
        threading.Thread(target=self._collect_news_thread, daemon=True).start()

    def _collect_news_thread(self):
        try:
            session = requests.Session()
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())

            all_items = []
            for url in self.feeds:
                try:
                    r = session.get(url, timeout=10,
                                    headers={"User-Agent": "Mozilla/5.0"},
                                    verify=certifi.where())
                    parsed = feedparser.parse(r.text, ssl_context=ssl_ctx)

                    for e in parsed.entries[:10]:
                        title = e.get("title", "")
                        link = e.get("link", "")
                        all_items.append((title, link))
                except Exception:
                    continue

            if not all_items:
                Clock.schedule_once(lambda *_: self._toast("No news collected."))
                return

            lines = []
            for i, (title, link) in enumerate(all_items, start=1):
                lines.append(f"{i}. {title}\n{link}\n")

            text_out = "\n".join(lines)
            Clock.schedule_once(lambda *_: self._toast(text_out))

        except Exception:
            err = traceback.format_exc()
            Clock.schedule_once(lambda *_: self._toast("Error collecting news:\n" + err))
        finally:
            self._loading = False

    # -----------------------------
    def send_emails_safe(self, *_):
        enabled_recs = [r["email"] for r in self.recipients if r.get("enabled")]
        if not enabled_recs:
            self._toast("No enabled recipients.")
            return
        if not self.senders:
            self._toast("No senders configured.")
            return

        self._toast("Sending emails...")
        threading.Thread(target=self._send_emails_thread, daemon=True).start()

    def _send_emails_thread(self):
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            body = self.status_label.text.strip()
            if not body or body.lower().startswith("collecting"):
                body = "No news content yet."

            subject = f"News Digest - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            enabled_recs = [r["email"] for r in self.recipients if r.get("enabled")]

            for s in self.senders:
                email = s.get("email")
                app_pass = s.get("app_password")

                if not email or not app_pass:
                    continue

                try:
                    msg = MIMEMultipart()
                    msg["From"] = email
                    msg["To"] = ", ".join(enabled_recs)
                    msg["Subject"] = subject
                    msg.attach(MIMEText(body, "plain", "utf-8"))

                    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20)
                    server.login(email, app_pass)
                    server.sendmail(email, enabled_recs, msg.as_string())
                    server.quit()

                    Clock.schedule_once(lambda *_: self._append_status(f"✅ Sent from {email}"))

                except Exception as e:
                    Clock.schedule_once(lambda *_: self._append_status(f"❌ Failed {email}: {e}"))

                time.sleep(2)

            Clock.schedule_once(lambda *_: self._append_status("Done."))

        except Exception:
            err = traceback.format_exc()
            Clock.schedule_once(lambda *_: self._append_status("Error sending:\n" + err))


if __name__ == "__main__":
    NewsApp().run()
