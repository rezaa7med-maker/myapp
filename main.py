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
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.core.window import Window


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


# -------------------------------------------------------------------
# SENT TITLES (no duplicates)
# -------------------------------------------------------------------
def load_sent_titles(path):
    try:
        if not os.path.exists(path):
            return set()
        with open(path, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except Exception:
        return set()


def append_sent_titles(path, titles):
    if not titles:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for t in titles:
                f.write(t.replace("\n", " ").strip() + "\n")
    except Exception:
        pass


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def collect_news_safe(log_func=print):
    import requests
    import feedparser

    items = []
    total_entries = 0

    for url in RSS_FEEDS:
        try:
            if CERT_PATH:
                r = requests.get(url, headers=REQUEST_HEADERS, timeout=10, verify=CERT_PATH)
            else:
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
        self.sent_path = os.path.join(self.user_data_dir, "sent_titles.txt")

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        title = Label(
            text="News Mailer (Safe Boot)",
            font_size="22sp",
            size_hint=(1, None),
            height=50
        )
        root.add_widget(title)

        scroll = ScrollView(size_hint=(1, 1))
        content = GridLayout(
            cols=1,
            size_hint_y=None,
            padding=10,
            spacing=10
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
                height=80,
                font_size="18sp",
                padding=[10, 10, 10, 10]
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
            height=56,
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
            height=220,
            halign="left",
            valign="top"
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        content.add_widget(self.status_label)

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
        self.set_status("Testing RSS ...")

        def task():
            try:
                items, total = collect_news_safe()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"RSS OK\nTotal entries: {total}\nCollected items: {len(items)}"
                    ), 0
                )
            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"RSS Error:\n{e}\n\n{tb}"
                    ), 0
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
        self.set_status("Sending (no duplicates)...")

        def task():
            try:
                sent_titles = load_sent_titles(self.sent_path)

                all_items, total = collect_news_safe()
                new_items = [(t, s) for (t, s) in all_items if t not in sent_titles]

                if not new_items:
                    Clock.schedule_once(
                        lambda dt: self.set_status("No new items to send."), 0
                    )
                    return

                new_items = new_items[:max_emails]

                ok, msg = send_emails_safe(sender, app_pass, to_emails, new_items)

                if ok:
                    titles_just_sent = [t for (t, _) in new_items]
                    append_sent_titles(self.sent_path, titles_just_sent)
                    out = f"{msg}\nSent new items: {len(new_items)}"
                else:
                    out = f"Send error:\n{msg}"

                Clock.schedule_once(lambda dt: self.set_status(out), 0)

            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: self.set_status(
                        f"Error:\n{e}\n\n{tb}"
                    ), 0
                )

        self.run_in_thread(task)


if __name__ == "__main__":
    NewsApp().run()
