import os
import json
import threading
import time
import traceback
import ssl
import smtplib
import base64

# -------------------------------------------------
#  FIX: old libs calling base64.decodestring (py3.9+ removed)
# -------------------------------------------------
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

import requests
import feedparser

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.scrollview import ScrollView


# --------- CONSTANT DATA ---------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}


# --------- FILE UTILS ---------
def write_crash(app_dir, text):
    try:
        os.makedirs(app_dir, exist_ok=True)
        path = os.path.join(app_dir, "crash.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def load_sent_titles(filename: str) -> set:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        return set(line for line in lines if line)
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


def append_sent_titles(filename: str, titles: list) -> None:
    if not titles:
        return
    try:
        with open(filename, "a", encoding="utf-8") as f:
            for title in titles:
                safe_title = title.replace("\n", " ")
                f.write(safe_title + "\n")
    except Exception:
        pass


# --------- RSS SAFE FETCH ---------
def collect_news_safe(log_func=print, timeout=10):
    items = []
    for url in RSS_FEEDS:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
            r.raise_for_status()

            feed = feedparser.parse(r.text)
            entries = getattr(feed, "entries", []) or []

            for entry in entries:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip() or title
                if title:
                    items.append((title, summary))

        except Exception as e:
            log_func(f"RSS error for {url}: {e}")
            continue

    return items


# --------- EMAIL ---------
def send_emails(sender_email, app_password, to_emails, news_items, log_func=print):
    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=15) as server:
        server.login(sender_email, app_password)

        for title, summary in news_items:
            subject = title
            body = summary

            msg = "\n".join([
                f"To: {', '.join(to_emails)}",
                f"Subject: {subject}",
                "",
                body
            ])

            server.sendmail(sender_email, to_emails, msg.encode("utf-8"))
            log_func(f"Sent: {subject}")


# --------- MAIN APP ---------
class NewsApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_file = None
        self.sent_file = None

        self.sender_input = None
        self.pass_input = None
        self.recipient_input = None
        self.max_emails_input = None
        self.status_label = None

    def build(self):
        Window.clearcolor = (0, 0, 0, 1)

        # --- Scroll root ---
        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(
            orientation="vertical",
            padding=20,
            spacing=12,
            size_hint_y=None
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)

        # --- Title ---
        title = Label(
            text="News Mailer (Safe Boot)",
            font_size="22sp",
            size_hint_y=None,
            height=60
        )
        content.add_widget(title)

        # --- Inputs ---
        def make_input(hint, password=False):
            return TextInput(
                hint_text=hint,
                multiline=False,
                password=password,
                size_hint_y=None,
                height=48
            )

        self.sender_input = make_input("Sender Gmail")
        self.pass_input = make_input("App Password (16 chars)", password=True)
        self.recipient_input = make_input("Recipient email")
        self.max_emails_input = make_input("Max emails")

        content.add_widget(self.sender_input)
        content.add_widget(self.pass_input)
        content.add_widget(self.recipient_input)
        content.add_widget(self.max_emails_input)

        # --- Buttons row ---
        btn_row = BoxLayout(
            orientation="horizontal",
            spacing=10,
            size_hint_y=None,
            height=55
        )

        test_btn = Button(text="Test RSS")
        send_btn = Button(text="Send")

        test_btn.bind(on_press=self.on_test_rss)
        send_btn.bind(on_press=self.on_send)

        btn_row.add_widget(test_btn)
        btn_row.add_widget(send_btn)
        content.add_widget(btn_row)

        # --- Status label ---
        self.status_label = Label(
            text="Ready.",
            font_size="16sp",
            size_hint_y=None,
            height=200,
            halign="left",
            valign="top"
        )
        self.status_label.bind(
            size=lambda *x: self.status_label.setter("text_size")(self.status_label, (self.status_label.width, None))
        )
        content.add_widget(self.status_label)

        return scroll

    def on_start(self):
        self.config_file = os.path.join(self.user_data_dir, "config.json")
        self.sent_file = os.path.join(self.user_data_dir, "sent_titles.txt")
        self.load_config()

    # --------- CONFIG ---------
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.sender_input.text = cfg.get("sender", "")
                self.pass_input.text = cfg.get("password", "")
                self.recipient_input.text = cfg.get("recipient", "")
                self.max_emails_input.text = str(cfg.get("max_emails", 3))
        except Exception:
            pass

    def save_config(self):
        try:
            cfg = {
                "sender": self.sender_input.text.strip(),
                "password": self.pass_input.text.strip(),
                "recipient": self.recipient_input.text.strip(),
                "max_emails": int(self.max_emails_input.text.strip() or "3"),
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # --------- UI LOG ---------
    def set_status(self, text):
        def _u(dt):
            self.status_label.text = text
        Clock.schedule_once(_u, 0)

    # --------- BUTTONS ---------
    def on_test_rss(self, _):
        self.set_status("Testing RSS ...")

        def worker():
            try:
                news = collect_news_safe(log_func=self.set_status)
                self.set_status(f"RSS OK, items: {len(news)}")
            except Exception as e:
                self.set_status(f"RSS FAILED: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_send(self, _):
        sender = self.sender_input.text.strip()
        password = self.pass_input.text.strip()
        recipient = self.recipient_input.text.strip()
        max_emails = int(self.max_emails_input.text.strip() or "3")

        if not sender or not password or not recipient:
            self.set_status("Fill sender, password, recipient.")
            return

        self.save_config()
        self.set_status("Collecting RSS ...")

        def worker():
            try:
                sent_titles = load_sent_titles(self.sent_file)
                all_items = collect_news_safe(log_func=self.set_status)

                new_items = [(t, s) for (t, s) in all_items if t not in sent_titles]
                if not new_items:
                    self.set_status("No new items.")
                    return

                to_send = new_items[:max_emails]
                self.set_status(f"Sending {len(to_send)} mails ...")

                send_emails(sender, password, [recipient], to_send, log_func=self.set_status)

                append_sent_titles(self.sent_file, [t for (t, _) in to_send])
                self.set_status("Done ✅")

            except Exception as e:
                tb = traceback.format_exc()
                self.set_status(f"ERROR: {e}")
                write_crash(self.user_data_dir, tb)

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    try:
        NewsApp().run()
    except Exception:
        tb = traceback.format_exc()
        try:
            write_crash("/sdcard", tb)
        except Exception:
            pass
        raise
