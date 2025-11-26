import os
import json
import threading
import traceback
import ssl
import smtplib
import base64

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.network.urlrequest import UrlRequest


# -------------------------------------------------------------------
# Fix for libraries that still call base64.decodestring/encodestring
# MUST be at top before anything uses base64 internally.
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


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def parse_feed_text(text, log_func=print):
    import feedparser

    items = []
    feed = feedparser.parse(text)
    entries = getattr(feed, "entries", []) or []

    for e in entries:
        title = getattr(e, "title", "").strip()
        summary = getattr(e, "summary", "").strip() or title
        if title:
            items.append((title, summary))

    return items, len(entries)


def collect_news_async(done_callback, log_func=print):
    """
    Collect RSS items asynchronously using UrlRequest
    to avoid ANR/UI freezes on Android.

    done_callback(items, total_entries)
    """
    items_all = []
    total_entries = 0
    idx = 0
    errors = []

    def fetch_next():
        nonlocal idx

        if idx >= len(RSS_FEEDS):
            done_callback(items_all, total_entries, errors)
            return

        url = RSS_FEEDS[idx]
        idx += 1

        def on_success(req, result):
            nonlocal total_entries
            try:
                feed_items, n = parse_feed_text(result, log_func=log_func)
                items_all.extend(feed_items)
                total_entries += n
            except Exception as e:
                errors.append(f"Parse error for {url}: {e}")
            fetch_next()

        def on_error(req, error):
            errors.append(f"RSS error for {url}: {error}")
            fetch_next()

        def on_failure(req, result):
            errors.append(f"RSS failure for {url}: {result}")
            fetch_next()

        UrlRequest(
            url,
            on_success=on_success,
            on_error=on_error,
            on_failure=on_failure,
            req_headers=REQUEST_HEADERS,
            timeout=10
        )

    fetch_next()


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

                    server.sendmail(
                        sender_email,
                        to_emails,
                        msg.encode("utf-8"),
                    )

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
            height=50
        )
        root.add_widget(title)

        content = BoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=10,
            spacing=12
        )
        root.add_widget(content)

        def make_input(hint, password=False):
            ti = TextInput(
                hint_text=hint,
                multiline=False,
                password=password,
                size_hint=(1, None),
                height=160,                 # bigger box
                font_size="18sp",          # same font size as before
                padding=[14, 18, 14, 18]   # more inner space, font unchanged
            )
            ti.bind(text=lambda *_: self.save_config())
            return ti

        self.sender_input = make_input("Sender Gmail")
        self.pass_input = make_input("App Password (16 chars)", password=True)
        self.recipient_input = make_input("Recipient email (comma separated)")
        self.max_emails_input = make_input("Max emails (number)")

        content.add_widget(Widget(size_hint=(1, 1)))

        content.add_widget(self.sender_input)
        content.add_widget(self.pass_input)
        content.add_widget(self.recipient_input)
        content.add_widget(self.max_emails_input)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=60,
            spacing=10
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
            height=240,
            halign="left",
            valign="top"
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        content.add_widget(self.status_label)

        content.add_widget(Widget(size_hint=(1, None), height=20))
        content.add_widget(Widget(size_hint=(1, 1)))

        self.load_config()
        return root

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
        self.test_btn.disabled = True
        self.set_status("Testing RSS ...")

        def done(items, total, errors):
            msg = f"RSS OK\nTotal entries: {total}\nCollected items: {len(items)}"
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors[:5])
            self.set_status(msg)
            self.test_btn.disabled = False

        try:
            collect_news_async(lambda items, total, errors: Clock.schedule_once(
                lambda dt: done(items, total, errors), 0
            ))
        except Exception as e:
            tb = traceback.format_exc()
            self.set_status(f"RSS Error:\n{e}\n\n{tb}")
            self.test_btn.disabled = False

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
        self.send_btn.disabled = True
        self.set_status("Collecting RSS before sending...")

        def after_collect(items, total, errors):
            items = items[:max_emails]
            self.set_status("Sending...")

            def send_task():
                try:
                    ok, msg = send_emails_safe(sender, app_pass, to_emails, items)
                    if ok:
                        out = f"{msg}\nSent items: {len(items)}"
                    else:
                        out = f"Send error:\n{msg}"
                    Clock.schedule_once(lambda dt: self._finish_send(out), 0)
                except Exception as e:
                    tb = traceback.format_exc()
                    Clock.schedule_once(lambda dt: self._finish_send(
                        f"Error:\n{e}\n\n{tb}"
                    ), 0)

            self.run_in_thread(send_task)

        collect_news_async(lambda items, total, errors: Clock.schedule_once(
            lambda dt: after_collect(items, total, errors), 0
        ))

    def _finish_send(self, text):
        self.set_status(text)
        self.send_btn.disabled = False


if __name__ == "__main__":
    NewsApp().run()
