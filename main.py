import os
import json
import threading
import traceback
import ssl
import smtplib
import base64
import time

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp


# -------------------------------------------------------------------
# Fix for libraries that still call base64.decodestring/encodestring
# -------------------------------------------------------------------
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes
if not hasattr(base64, "encodestring"):
    base64.encodestring = base64.encodebytes


# -------------------------------------------------------------------
# Optional certifi (better SSL on Android)
# -------------------------------------------------------------------
try:
    import certifi
    CERT_PATH = certifi.where()
    os.environ["SSL_CERT_FILE"] = CERT_PATH
    os.environ["REQUESTS_CA_BUNDLE"] = CERT_PATH
except Exception:
    CERT_PATH = None


# -------------------------------------------------------------------
# CONSTANTS
# -------------------------------------------------------------------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}

RSS_PER_FEED_TIMEOUT = (5, 8)
RSS_TOTAL_TIMEOUT = 20


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def collect_news_safe(log_func=print):
    import requests
    import feedparser

    items = []
    total_entries = 0
    lock = threading.Lock()

    def fetch_one(url):
        nonlocal total_entries
        try:
            kwargs = dict(headers=REQUEST_HEADERS, timeout=RSS_PER_FEED_TIMEOUT)
            if CERT_PATH:
                kwargs["verify"] = CERT_PATH

            r = requests.get(url, **kwargs)
            r.raise_for_status()

            feed = feedparser.parse(r.text)
            entries = getattr(feed, "entries", []) or []

            local_items = []
            for e in entries:
                title = getattr(e, "title", "").strip()
                summary = getattr(e, "summary", "").strip() or title
                if title:
                    local_items.append((title, summary))

            with lock:
                total_entries += len(entries)
                items.extend(local_items)

        except Exception as e:
            log_func(f"RSS error for {url}: {e}")

    threads = []
    for url in RSS_FEEDS:
        t = threading.Thread(target=fetch_one, args=(url,), daemon=True)
        threads.append(t)
        t.start()

    start = time.time()
    for t in threads:
        remaining = RSS_TOTAL_TIMEOUT - (time.time() - start)
        if remaining <= 0:
            break
        t.join(timeout=remaining)

    return items, total_entries


def send_emails_safe(sender_email, app_password, to_emails, news_items):
    last_err = None

    for verified in (True, False):
        try:
            if verified:
                if CERT_PATH:
                    context = ssl.create_default_context(cafile=CERT_PATH)
                else:
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

            return True, ("Sent with verified SSL"
                          if verified else
                          "Sent without SSL verification")

        except Exception as e:
            last_err = e
            if verified and "CERTIFICATE_VERIFY_FAILED" in str(e):
                continue
            break

    return False, str(last_err)


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)
        self.config_path = os.path.join(self.user_data_dir, "config.json")

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        title = Label(
            text="News Mailer (Safe Boot)",
            font_size="22sp",
            size_hint=(1, None),
            height=dp(50)
        )
        root.add_widget(title)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=dp(10),
            spacing=dp(10)
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
                height=dp(160),
                font_size="18sp",
                padding=[dp(10), dp(12), dp(10), dp(12)]
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
            height=dp(60),
            spacing=dp(10)
        )
        self.test_btn = Button(text="Test RSS")
        self.send_btn = Button(text="Send")
        self.test_btn.bind(on_release=self.on_test_rss)
        self.send_btn.bind(on_release=self.on_send)
        btn_row.add_widget(self.test_btn)
        btn_row.add_widget(self.send_btn)
        content.add_widget(btn_row)

        self.status_label = Label(
            text="Ready...",
            font_size="16sp",
            size_hint=(1, None),
            height=dp(220),
            halign="left",
            valign="top"
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        content.add_widget(self.status_label)

        # Spacer to keep ScrollView draggable even when content is short
        content.add_widget(Widget(size_hint=(1, None), height=dp(260)))

        self.load_config()
        return root

    def on_pause(self):
        return True

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

    def set_buttons_enabled(self, enabled: bool):
        self.test_btn.disabled = not enabled
        self.send_btn.disabled = not enabled

    # ---------------- ACTIONS ----------------
    def on_test_rss(self, *_):
        self.set_buttons_enabled(False)
        self.set_status("Testing RSS ...")

        def task():
            start = time.time()
            try:
                items, total = collect_news_safe()
                elapsed = time.time() - start
                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(
                            f"RSS OK\n"
                            f"Total entries: {total}\n"
                            f"Collected items: {len(items)}\n"
                            f"Elapsed: {elapsed:.1f}s"
                        ),
                        self.set_buttons_enabled(True)
                    ),
                    0
                )
            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(f"RSS Error:\n{e}\n\n{tb}"),
                        self.set_buttons_enabled(True)
                    ),
                    0
                )

        self.run_in_thread(task)

    def on_send(self, *_):
        sender = self.sender_input.text.strip()
        app_pass = self.pass_input.text.strip()
        recipient_raw = self.recipient_input.text.strip()
        max_raw = self.max_emails_input.text.strip()

        if not sender or not app_pass or not recipient_raw:
            self.set_status("Please fill sender, app password, and recipient.")
            return

        try:
            max_emails = int(max_raw) if max_raw else 5
        except ValueError:
            max_emails = 5

        to_emails = [x.strip() for x in recipient_raw.split(",") if x.strip()]
        self.set_buttons_enabled(False)
        self.set_status("Sending...")

        def task():
            try:
                news_items, total = collect_news_safe()
                news_items = news_items[:max_emails]

                ok, msg = send_emails_safe(sender, app_pass, to_emails, news_items)

                if ok:
                    out = f"{msg}\nSent items: {len(news_items)}"
                else:
                    out = f"Send error:\n{msg}"

                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(out),
                        self.set_buttons_enabled(True)
                    ),
                    0
                )

            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(f"Error:\n{e}\n\n{tb}"),
                        self.set_buttons_enabled(True)
                    ),
                    0
                )

        self.run_in_thread(task)


if __name__ == "__main__":
    NewsApp().run()
