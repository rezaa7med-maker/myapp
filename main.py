import os
import json
import threading
import time
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.modalview import ModalView
from kivy.clock import Clock
from kivy.core.window import Window


# ---------- PATCH FOR PYTHON 3.12 ----------
# بعضی کتابخونه‌ها هنوز decodestring صدا میزنن
import base64
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes


# ---------- CONSTANTS ----------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}


def safe_write(app_dir, name, text):
    try:
        os.makedirs(app_dir, exist_ok=True)
        path = os.path.join(app_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def collect_news_safe(log_func=print):
    items = []
    try:
        import requests
        import feedparser
    except Exception as e:
        log_func(f"IMPORT ERROR: {e}")
        return items

    for url in RSS_FEEDS:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
            r.raise_for_status()

            feed = feedparser.parse(r.text)
            entries = getattr(feed, "entries", []) or []

            for entry in entries:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip() or title
                if title:
                    items.append((title, summary))

        except Exception as e:
            log_func(f"RSS ERROR {url}: {e}")

    return items


def send_emails_safe(sender_email, app_password, to_emails, news_items, log_func=print):
    try:
        import ssl
        import smtplib
    except Exception as e:
        log_func(f"IMPORT ERROR SMTP/SSL: {e}")
        return

    try:
        context = ssl.create_default_context()

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)

            for title, summary in news_items:
                message_lines = [
                    f"To: {', '.join(to_emails)}",
                    f"Subject: {title}",
                    "",
                    summary,
                ]
                message = "\n".join(message_lines)

                server.sendmail(sender_email, to_emails, message.encode("utf-8"))
                log_func(f"SENT: {title}")

    except Exception as e:
        log_func(f"SMTP ERROR: {e}")
        raise


class NewsApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.status_label = None
        self.max_emails_input = None
        self.sender_input = None
        self.pass_input = None
        self.recipient_input = None

    def build(self):
        Window.clearcolor = (0, 0, 0, 1)

        root = BoxLayout(orientation="vertical", padding=20, spacing=10)

        root.add_widget(Label(text="News Mailer (Safe Boot)", font_size="20sp"))

        self.sender_input = TextInput(hint_text="Sender Gmail", multiline=False)
        self.pass_input = TextInput(hint_text="App Password", multiline=False, password=True)
        self.recipient_input = TextInput(hint_text="Recipient email", multiline=False)
        self.max_emails_input = TextInput(hint_text="Max emails", multiline=False, input_filter="int")

        root.add_widget(self.sender_input)
        root.add_widget(self.pass_input)
        root.add_widget(self.recipient_input)
        root.add_widget(self.max_emails_input)

        btn_rss = Button(text="Test RSS")
        btn_send = Button(text="Send")
        btn_rss.bind(on_press=self.on_test_rss)
        btn_send.bind(on_press=self.on_send)

        root.add_widget(btn_rss)
        root.add_widget(btn_send)

        self.status_label = Label(text="Ready.", font_size="16sp")
        root.add_widget(self.status_label)

        return root

    def log(self, msg):
        def _u(dt):
            self.status_label.text = msg
        Clock.schedule_once(_u, 0)

    def on_test_rss(self, _):
        self.log("Testing RSS...")
        threading.Thread(target=self._test_rss_thread, daemon=True).start()

    def _test_rss_thread(self):
        try:
            news = collect_news_safe(log_func=self.log)
            self.log(f"RSS OK, items: {len(news)}")
        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"RSS CRASH: {e}")
            safe_write(self.user_data_dir, "crash.txt", tb)

    def on_send(self, _):
        self.log("Sending...")
        threading.Thread(target=self._send_thread, daemon=True).start()

    def _send_thread(self):
        try:
            sender = self.sender_input.text.strip()
            pw = self.pass_input.text.strip()
            rec = self.recipient_input.text.strip()
            max_n = int(self.max_emails_input.text.strip() or "2")

            news = collect_news_safe(log_func=self.log)
            to_send = news[:max_n]

            send_emails_safe(sender, pw, [rec], to_send, log_func=self.log)
            self.log("Done!")

        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"ERROR: {e}")
            safe_write(self.user_data_dir, "crash.txt", tb)


if __name__ == "__main__":
    NewsApp().run()
