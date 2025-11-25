import os
import threading
import ssl
import smtplib
import time
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.core.window import Window


# ---------------- CONSTANTS ----------------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT_STARTTLS = 587
SMTP_TIMEOUT = 15
SMTP_RETRIES = 2


# ---------------- HELPERS ----------------
def write_crash(app_dir, text):
    try:
        os.makedirs(app_dir, exist_ok=True)
        path = os.path.join(app_dir, "crash.txt")
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
        log_func(f"Import error: {e}")
        return items

    for url in RSS_FEEDS:
        try:
            log_func(f"Fetching: {url}")

            r = requests.get(
                url,
                headers=REQUEST_HEADERS,
                timeout=12,
                allow_redirects=True
            )

            log_func(f"Status {r.status_code} | bytes={len(r.content)}")

            if r.status_code != 200:
                continue

            feed = feedparser.parse(r.content)

            if getattr(feed, "bozo", False):
                be = getattr(feed, "bozo_exception", None)
                log_func(f"Parse warning: {be}")

            entries = getattr(feed, "entries", []) or []
            log_func(f"Items in this feed: {len(entries)}")

            for entry in entries:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip() or title
                if title:
                    items.append((title, summary))

        except Exception as e:
            log_func(f"RSS error for {url}: {e}")
            continue

    return items


def send_emails_starttls(sender_email, app_password, to_emails, news_items, log_func=print):
    context = ssl.create_default_context()
    last_err = None

    for attempt in range(SMTP_RETRIES + 1):
        try:
            log_func(f"SMTP connect... (try {attempt+1})")
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT_STARTTLS, timeout=SMTP_TIMEOUT)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()

            server.login(sender_email, app_password)

            for title, summary in news_items:
                subject = title
                body = summary

                message_lines = [
                    f"To: {', '.join(to_emails)}",
                    f"Subject: {subject}",
                    "Content-Type: text/plain; charset=utf-8",
                    "",
                    body,
                ]
                message = "\n".join(message_lines)

                server.sendmail(
                    sender_email,
                    to_emails,
                    message.encode("utf-8"),
                )
                log_func(f"Sent: {subject}")

            server.quit()
            return

        except Exception as e:
            last_err = e
            log_func(f"SMTP error: {e}")
            try:
                server.quit()
            except Exception:
                pass
            time.sleep(1.5)

    raise last_err


# ---------------- APP ----------------
class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)

        # Scroll root so UI never squishes
        scroll = ScrollView(size_hint=(1, 1))
        root = BoxLayout(
            orientation="vertical",
            padding=20,
            spacing=12,
            size_hint_y=None
        )
        root.bind(minimum_height=root.setter("height"))
        scroll.add_widget(root)

        self.title_label = Label(
            text="News Mailer (Safe Boot)",
            font_size="22sp",
            size_hint=(1, None),
            height=60,
        )

        self.sender_input = TextInput(
            hint_text="Sender Gmail",
            multiline=False,
            size_hint=(1, None),
            height=55,
            font_size="18sp",
        )

        self.pass_input = TextInput(
            hint_text="App Password (16 chars)",
            password=True,
            multiline=False,
            size_hint=(1, None),
            height=55,
            font_size="18sp",
        )

        self.recipient_input = TextInput(
            hint_text="Recipient email",
            multiline=False,
            size_hint=(1, None),
            height=55,
            font_size="18sp",
        )

        self.max_input = TextInput(
            hint_text="Max emails",
            input_filter="int",
            multiline=False,
            size_hint=(1, None),
            height=55,
            font_size="18sp",
        )

        self.test_btn = Button(
            text="Test RSS",
            size_hint=(1, None),
            height=65,
            font_size="20sp",
        )
        self.send_btn = Button(
            text="Send",
            size_hint=(1, None),
            height=65,
            font_size="20sp",
        )

        self.test_btn.bind(on_press=self.on_test_rss)
        self.send_btn.bind(on_press=self.on_send)

        self.status_label = Label(
            text="Ready.",
            font_size="16sp",
            size_hint=(1, None),
            height=400,
            halign="left",
            valign="top",
        )
        self.status_label.bind(size=lambda inst, val: inst.setter("text_size")(inst, val))

        root.add_widget(self.title_label)
        root.add_widget(self.sender_input)
        root.add_widget(self.pass_input)
        root.add_widget(self.recipient_input)
        root.add_widget(self.max_input)
        root.add_widget(self.test_btn)
        root.add_widget(self.send_btn)
        root.add_widget(self.status_label)

        return scroll

    def log(self, msg):
        def _u(dt):
            self.status_label.text += ("\n" + msg)
        Clock.schedule_once(_u, 0)

    def clear_log(self):
        def _c(dt):
            self.status_label.text = ""
        Clock.schedule_once(_c, 0)

    def on_test_rss(self, instance):
        self.clear_log()
        self.log("Testing RSS ...")
        t = threading.Thread(target=self._test_rss_bg, daemon=True)
        t.start()

    def _test_rss_bg(self):
        try:
            news = collect_news_safe(log_func=self.log)
            self.log(f"TOTAL items collected: {len(news)}")
        except Exception as e:
            self.log(f"RSS ERROR: {e}")

    def on_send(self, instance):
        sender = self.sender_input.text.strip()
        app_pass = self.pass_input.text.strip()
        recipient = self.recipient_input.text.strip()
        max_text = self.max_input.text.strip()

        if not sender or not app_pass or not recipient:
            self.log("Fill sender, password, recipient.")
            return

        try:
            max_emails = int(max_text) if max_text else 2
            if max_emails <= 0:
                max_emails = 1
        except Exception:
            max_emails = 2

        self.send_btn.disabled = True
        self.log("Sending...")

        t = threading.Thread(
            target=self._send_bg,
            args=(sender, app_pass, [recipient], max_emails),
            daemon=True
        )
        t.start()

    def _send_bg(self, sender, app_pass, recipients, max_emails):
        try:
            news = collect_news_safe(log_func=self.log)
            if not news:
                self.log("No news to send.")
                return

            to_send = news[:max_emails]
            self.log(f"SMTP send {len(to_send)} items...")

            send_emails_starttls(sender, app_pass, recipients, to_send, log_func=self.log)

            self.log("Done! Emails sent.")

        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"ERROR: {e}")

            try:
                app_dir = self.user_data_dir
            except Exception:
                app_dir = "/sdcard"
            write_crash(app_dir, tb)

        finally:
            def _enable(dt):
                self.send_btn.disabled = False
            Clock.schedule_once(_enable, 0)


if __name__ == "__main__":
    NewsApp().run()
