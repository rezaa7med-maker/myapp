import os
import json
import threading
import traceback
import ssl
import smtplib
import base64

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.resources import resource_find


# ---------------------------------------------------------
# Fix for libs that still call base64.decodestring/encodestring
# ---------------------------------------------------------
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes
if not hasattr(base64, "encodestring"):
    base64.encodestring = base64.encodebytes


# ---------------------------------------------------------
# Persian font setup
# font file: fonts/Vazirmatn-Regular.ttf
# ---------------------------------------------------------
FONT_NAME = "Vazirmatn"
FONT_REL_PATH = os.path.join("fonts", "Vazirmatn-Regular.ttf")
FONT_PATH = resource_find(FONT_REL_PATH) or FONT_REL_PATH

try:
    LabelBase.register(name=FONT_NAME, fn_regular=FONT_PATH)
except Exception:
    FONT_NAME = None


# ---------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def collect_news_safe(log_func=print):
    import requests
    import feedparser

    items = []
    total_entries = 0

    for url in RSS_FEEDS:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
            r.raise_for_status()

            feed = feedparser.parse(r.text)
            entries = getattr(feed, "entries", []) or []
            total_entries += len(entries)

            for e in entries:
                title = getattr(e, "title", "").strip()
                summary = getattr(e, "summary", "").strip() or title
                if title:
                    items.append((title, summary))

        except Exception as e:
            log_func(f"RSS error for {url}: {e}")

    return items, total_entries


def _send_via_smtp_ssl(sender_email, app_password, to_emails, news_items, verify_ssl=True):
    if verify_ssl:
        context = ssl.create_default_context()
    else:
        context = ssl._create_unverified_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=20) as server:
        server.login(sender_email, app_password)
        for title, summary in news_items:
            msg = "\n".join([
                f"To: {', '.join(to_emails)}",
                f"Subject: {title}",
                "",
                summary,
            ])
            server.sendmail(sender_email, to_emails, msg.encode("utf-8"))


def _send_via_starttls(sender_email, app_password, to_emails, news_items, verify_ssl=True):
    context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(sender_email, app_password)
        for title, summary in news_items:
            msg = "\n".join([
                f"To: {', '.join(to_emails)}",
                f"Subject: {title}",
                "",
                summary,
            ])
            server.sendmail(sender_email, to_emails, msg.encode("utf-8"))


def send_emails_safe(sender_email, app_password, to_emails, news_items):
    last_err = None

    attempts = [
        ("SSL-465 (verify)", lambda: _send_via_smtp_ssl(sender_email, app_password, to_emails, news_items, True)),
        ("SSL-465 (no-verify)", lambda: _send_via_smtp_ssl(sender_email, app_password, to_emails, news_items, False)),
        ("STARTTLS-587 (verify)", lambda: _send_via_starttls(sender_email, app_password, to_emails, news_items, True)),
        ("STARTTLS-587 (no-verify)", lambda: _send_via_starttls(sender_email, app_password, to_emails, news_items, False)),
    ]

    for label, fn in attempts:
        try:
            fn()
            return True, f"ارسال موفق با روش: {label}"
        except Exception as e:
            last_err = e

    return False, str(last_err)


# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------
class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)
        Window.softinput_mode = "below_target"

        self.config_path = os.path.join(self.user_data_dir, "config.json")

        root = BoxLayout(orientation="vertical", padding=12, spacing=12)

        title = Label(
            text="News Mailer (Safe Boot)",
            font_size="22sp",
            size_hint=(1, None),
            height=52,
            font_name=FONT_NAME if FONT_NAME else None
        )
        root.add_widget(title)

        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=10,
            spacing=12
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        def make_input(hint, password=False):
            ti = TextInput(
                hint_text=hint,
                multiline=False,
                password=password,
                size_hint=(1, None),
                height=60,
                font_size="18sp",
                font_name=FONT_NAME if FONT_NAME else None
            )
            ti.bind(text=lambda *_: self.save_config())
            return ti

        self.sender_input = make_input("Sender Gmail")
        self.pass_input = make_input("App Password (16 chars)", password=True)
        self.recipient_input = make_input("Recipient email (comma separated)")
        self.max_emails_input = make_input("Max emails (number)")

        content.add_widget(self.sender_input)
        content.add_widget(self.pass_input)
        content.add_widget(self.recipient_input)
        content.add_widget(self.max_emails_input)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=62,
            spacing=12
        )

        self.test_btn = Button(
            text="Test RSS",
            size_hint=(1, 1),
            font_name=FONT_NAME if FONT_NAME else None
        )
        self.send_btn = Button(
            text="Send",
            size_hint=(1, 1),
            font_name=FONT_NAME if FONT_NAME else None
        )

        self.test_btn.bind(on_release=self.on_test_rss)
        self.send_btn.bind(on_release=self.on_send)

        btn_row.add_widget(self.test_btn)
        btn_row.add_widget(self.send_btn)
        content.add_widget(btn_row)

        self.status_label = Label(
            text="آماده...",
            font_size="16sp",
            size_hint=(1, None),
            height=200,
            halign="left",
            valign="top",
            font_name=FONT_NAME if FONT_NAME else None
        )
        self.status_label.bind(size=lambda *_: self._update_text_size())
        content.add_widget(self.status_label)

        # spacer to avoid everything sticking to top visually
        content.add_widget(Widget(size_hint=(1, None), height=40))

        if FONT_NAME is None:
            self.set_status("فونت پیدا نشد. مطمئن شو فایل fonts/Vazirmatn-Regular.ttf داخل پروژه هست و پسوند ttf تو buildozer اضافه شده.")

        self.load_config()
        return root

    def _update_text_size(self):
        self.status_label.text_size = (self.status_label.width, None)

    # ---------------- CONFIG ----------------
    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.sender_input.text = data.get("sender", "")
                self.pass_input.text = data.get("app_password", "")
                self.recipient_input.text = data.get("recipient", "")
                self.max_emails_input.text = str(data.get("max_emails", ""))
        except Exception:
            pass

    def save_config(self):
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            data = {
                "sender": self.sender_input.text.strip(),
                "app_password": self.pass_input.text.strip(),
                "recipient": self.recipient_input.text.strip(),
                "max_emails": self.max_emails_input.text.strip(),
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def on_stop(self):
        self.save_config()

    # ---------------- UI HELPERS ----------------
    def set_status(self, text):
        self.status_label.text = text

    def run_in_thread(self, func):
        t = threading.Thread(target=func, daemon=True)
        t.start()

    # ---------------- ACTIONS ----------------
    def on_test_rss(self, *_):
        self.set_status("در حال تست RSS ...")

        def task():
            try:
                items, total = collect_news_safe()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"RSS OK ✅\nتعداد کل ورودی‌ها: {total}\nتعداد خبرهای جمع‌آوری‌شده: {len(items)}"
                    ), 0
                )
            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"خطا در RSS:\n{e}\n\n{tb}"
                    ), 0
                )

        self.run_in_thread(task)

    def on_send(self, *_):
        sender = self.sender_input.text.strip()
        app_pass = self.pass_input.text.strip()
        recipient_raw = self.recipient_input.text.strip()
        max_raw = self.max_emails_input.text.strip()

        if not sender or not app_pass or not recipient_raw:
            self.set_status("لطفاً فرستنده، رمز اپ و گیرنده را کامل وارد کن.")
            return

        try:
            max_emails = int(max_raw) if max_raw else 5
        except ValueError:
            max_emails = 5

        to_emails = [x.strip() for x in recipient_raw.split(",") if x.strip()]
        self.set_status("در حال ارسال...")

        def task():
            try:
                news_items, total = collect_news_safe()
                news_items = news_items[:max_emails]

                if not news_items:
                    Clock.schedule_once(lambda dt: self.set_status("هیچ خبری برای ارسال پیدا نشد."), 0)
                    return

                ok, msg = send_emails_safe(sender, app_pass, to_emails, news_items)

                if ok:
                    out = f"{msg}\nارسال شد: {len(news_items)} خبر"
                else:
                    out = f"خطا هنگام ارسال:\n{msg}\n\n(احتمالاً بدون VPN یا شبکه‌ی محدودشده به Gmail وصل هستی)"

                Clock.schedule_once(lambda dt: self.set_status(out), 0)

            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"خطا:\n{e}\n\n{tb}"
                    ), 0
                )

        self.run_in_thread(task)


if __name__ == "__main__":
    NewsApp().run()
