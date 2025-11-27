import os
import json
import threading
import traceback
import ssl
import smtplib
import base64
import time
import random

from kivy.config import Config
Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "borderless", "0")
Config.set("graphics", "resizable", "1")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.graphics import Color, Line, Rectangle


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

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"}

RSS_PER_FEED_TIMEOUT = (5, 8)
RSS_TOTAL_TIMEOUT = 20

EMAIL_DELAY_RANGE = (2.5, 6.0)
SENDER_DELAY_RANGE = (3.0, 8.0)

LIGHT_BLUE = (0.3, 0.65, 1.0, 1.0)
LIGHT_GREEN = (0.0, 0.8, 0.0, 1.0)
LIGHT_PURPLE = (0.75, 0.45, 1.0, 1.0)
CREAM_WHITE = (0.96, 0.96, 0.88, 1.0)
NORMAL_GREEN = (0.0, 0.8, 0.0, 1.0)
RED = (1.0, 0.4, 0.4, 1.0)

BTN_HEIGHT = dp(46)


# -------------------------------------------------------------------
# SENT TITLES HELPERS
# -------------------------------------------------------------------
def normalize_title(t):
    return " ".join((t or "").split()).strip()


def load_sent_titles(path):
    if not os.path.exists(path):
        return set()
    out = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                title = normalize_title(line)
                if title:
                    out.add(title)
    except Exception:
        pass
    return out


def append_sent_titles(path, titles):
    if not titles:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for t in titles:
                f.write(normalize_title(t).replace("\n", " ") + "\n")
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
                title = normalize_title(getattr(e, "title", ""))
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


def send_emails_safe(sender_email, app_password, to_emails, news_items, progress_cb=None):
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

            with smtplib.SMTP_SSL(
                "smtp.gmail.com", 465, context=context, timeout=20
            ) as server:
                server.login(sender_email, app_password)

                total_n = len(news_items)
                for i, (title, summary) in enumerate(news_items):
                    if progress_cb:
                        try:
                            progress_cb(i + 1, total_n)
                        except Exception:
                            pass

                    msg = "\n".join(
                        [
                            f"To: {', '.join(to_emails)}",
                            f"Subject: {title}",
                            "",
                            summary,
                        ]
                    )
                    server.sendmail(
                        sender_email, to_emails, msg.encode("utf-8")
                    )

                    if i < total_n - 1:
                        time.sleep(random.uniform(*EMAIL_DELAY_RANGE))

            return True, (
                "Sent with verified SSL"
                if verified
                else "Sent without SSL verification"
            )

        except Exception as e:
            last_err = e
            if verified and "CERTIFICATE_VERIFY_FAILED" in str(e):
                continue
            break

    return False, str(last_err)


# -------------------------------------------------------------------
# UI ROW FOR SENDERS / RECIPIENTS
# -------------------------------------------------------------------
class SenderRow(BoxLayout):
    def __init__(self, text, on_delete, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(6),
            **kwargs,
        )

        self.lbl = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_x=0.89,
            font_size="15sp",
        )
        self.lbl.bind(
            size=lambda inst, *_: setattr(
                inst, "text_size", (inst.width, None)
            )
        )

        btn_del = Button(text="×", size_hint_x=0.11, font_size="16sp")
        btn_del.bind(on_release=lambda *_: on_delete())

        self.add_widget(self.lbl)
        self.add_widget(btn_del)


class RecipientRow(BoxLayout):
    def __init__(self, text, on_delete, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(6),
            **kwargs,
        )

        self.lbl = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_x=0.89,
            font_size="15sp",
        )
        self.lbl.bind(
            size=lambda inst, *_: setattr(
                inst, "text_size", (inst.width, None)
            )
        )

        btn_del = Button(text="×", size_hint_x=0.11, font_size="16sp")
        btn_del.bind(on_release=lambda *_: on_delete())

        self.add_widget(self.lbl)
        self.add_widget(btn_del)


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)
        Window.fullscreen = False

        self.config_path = os.path.join(self.user_data_dir, "config.json")
        self.sent_titles_path = os.path.join(self.user_data_dir, "sent_titles.txt")

        self.senders = []
        self.recipients = []
        self.sent_titles = set()
        self.max_emails_value = 20

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        top_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=BTN_HEIGHT,
        )
        menu_btn = Button(
            text="[b]MENU[/b]",
            markup=True,
            size_hint=(None, None),
            width=BTN_HEIGHT,
            height=BTN_HEIGHT,
            font_size="14sp",
            background_normal="",
            background_color=CREAM_WHITE,
            color=(0, 0, 0, 1),
        )
        menu_btn.bind(on_release=lambda *_: self.show_menu_popup())
        top_bar.add_widget(menu_btn)
        top_bar.add_widget(Widget())
        root.add_widget(top_bar)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=dp(10),
            spacing=dp(10),
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        self.senders_box = self.build_senders_box()
        content.add_widget(self.senders_box)

        self.recipients_box = self.build_recipients_box()
        content.add_widget(self.recipients_box)

        self.max_emails_btn = Button(
            text=f"Max emails: {self.max_emails_value}",
            size_hint=(1, None),
            height=BTN_HEIGHT,
            font_size="16sp",
            background_normal="",
            background_color=CREAM_WHITE,
            color=(0, 0, 0, 1),
        )
        self.max_emails_btn.bind(on_release=lambda *_: self.show_max_emails_popup())
        content.add_widget(self.max_emails_btn)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=BTN_HEIGHT,
            spacing=dp(10),
        )
        self.test_btn = Button(
            text="Test RSS",
            background_normal="",
            background_color=LIGHT_PURPLE,
        )
        self.send_btn = Button(
            text="Send",
            background_normal="",
            background_color=LIGHT_GREEN,
        )
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
            valign="top",
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        content.add_widget(self.status_label)

        content.add_widget(Widget(size_hint=(1, None), height=dp(90)))

        self.load_config()
        self.sent_titles = load_sent_titles(self.sent_titles_path)
        self.refresh_senders_list()
        self.refresh_recipients_list()
        return root

    def on_start(self):
        Window.fullscreen = False

        def show_bars(*_):
            try:
                from jnius import autoclass
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                View = autoclass("android.view.View")
                activity = PythonActivity.mActivity
                decor = activity.getWindow().getDecorView()
                decor.setSystemUiVisibility(0)
            except Exception:
                pass

        show_bars()
        Clock.schedule_interval(show_bars, 0.5)

        Window.bind(on_keyboard=self.on_keyboard)

    def on_resume(self):
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            View = autoclass("android.view.View")
            activity = PythonActivity.mActivity
            decor = activity.getWindow().getDecorView()
            decor.setSystemUiVisibility(0)
        except Exception:
            pass
        return True

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key == 27:
            self.show_exit_confirm()
            return True
        return False

    def show_menu_popup(self):
        wrapper = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        reset_btn = Button(text="Reset RSS", size_hint_y=None, height=BTN_HEIGHT)
        exit_btn = Button(text="Exit", size_hint_y=None, height=BTN_HEIGHT)
        wrapper.add_widget(reset_btn)
        wrapper.add_widget(exit_btn)

        popup = Popup(
            title="Menu",
            content=wrapper,
            size_hint=(0.6, None),
            height=dp(200),
            auto_dismiss=True,
        )
        reset_btn.bind(on_release=lambda *_: (popup.dismiss(), self.reset_rss()))
        exit_btn.bind(on_release=lambda *_: (popup.dismiss(), self.stop()))
        popup.open()

    def reset_rss(self):
        try:
            if self.sent_titles_path:
                os.makedirs(self.user_data_dir, exist_ok=True)
                with open(self.sent_titles_path, "w", encoding="utf-8") as f:
                    f.write("")
        except Exception:
            pass
        self.sent_titles = set()
        self.set_status("RSS reset.")

    def show_exit_confirm(self):
        self.show_confirm(
            title="Exit?",
            message="Exit?",
            yes_text="Yes, I'm sure",
            no_text="Cancel",
            on_yes=self.stop,
        )

    def show_send_confirm(self):
        self.show_confirm(
            title="Send?",
            message="Send?",
            yes_text="Yes, I'm sure",
            no_text="Cancel",
            on_yes=self.do_send,
        )

    def show_delete_confirm(self, on_yes):
        self.show_confirm(
            title="Delete?",
            message="Delete?",
            yes_text="Yes, I'm sure",
            no_text="Cancel",
            on_yes=on_yes,
        )

    def show_confirm(self, title, message, yes_text, no_text, on_yes):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        content.add_widget(Label(text=message))

        btns = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(6),
        )
        yes_btn = Button(text=yes_text, background_normal="", background_color=NORMAL_GREEN)
        no_btn = Button(text=no_text, background_normal="", background_color=RED)
        btns.add_widget(yes_btn)
        btns.add_widget(no_btn)
        content.add_widget(btns)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.85, None),
            height=dp(200),
            auto_dismiss=False,
        )
        yes_btn.bind(on_release=lambda *_: (popup.dismiss(), on_yes()))
        no_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def build_senders_box(self):
        box = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(220),
            spacing=dp(6),
            padding=dp(6),
        )

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=BTN_HEIGHT,
            spacing=dp(6),
        )
        header.add_widget(
            Label(
                text="Senders",
                halign="left",
                valign="middle",
                font_size="16sp",
            )
        )
        add_btn = Button(
            text="Add Sender",
            size_hint=(None, None),
            width=dp(140),
            height=BTN_HEIGHT,
            font_size="14sp",
            background_normal="",
            background_color=LIGHT_BLUE,
        )
        add_btn.bind(on_release=lambda *_: self.show_sender_form_popup())
        header.add_widget(add_btn)
        box.add_widget(header)

        self.senders_list_layout = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self.senders_list_layout.bind(
            minimum_height=self.senders_list_layout.setter("height")
        )

        list_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        list_scroll.add_widget(self.senders_list_layout)

        list_container = BoxLayout(size_hint=(1, 1), padding=dp(4))
        with list_container.canvas.before:
            Color(0.12, 0.12, 0.12, 1)
            bg = Rectangle(pos=list_container.pos, size=list_container.size)
        with list_container.canvas.after:
            Color(0.5, 0.5, 0.5, 1)
            border = Line(rectangle=(*list_container.pos, *list_container.size), width=1.2)

        def upd(*_):
            bg.pos = list_container.pos
            bg.size = list_container.size
            border.rectangle = (*list_container.pos, *list_container.size)

        list_container.bind(pos=upd, size=upd)
        list_container.add_widget(list_scroll)
        box.add_widget(list_container)

        return box

    def build_recipients_box(self):
        box = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(220),
            spacing=dp(6),
            padding=dp(6),
        )

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=BTN_HEIGHT,
            spacing=dp(6),
        )
        header.add_widget(
            Label(
                text="Recipients",
                halign="left",
                valign="middle",
                font_size="16sp",
            )
        )
        add_btn = Button(
            text="Add Recipient",
            size_hint=(None, None),
            width=dp(140),
            height=BTN_HEIGHT,
            font_size="14sp",
            background_normal="",
            background_color=LIGHT_BLUE,
        )
        add_btn.bind(on_release=lambda *_: self.show_recipient_form_popup())
        header.add_widget(add_btn)
        box.add_widget(header)

        self.recipients_list_layout = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self.recipients_list_layout.bind(
            minimum_height=self.recipients_list_layout.setter("height")
        )

        list_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        list_scroll.add_widget(self.recipients_list_layout)

        list_container = BoxLayout(size_hint=(1, 1), padding=dp(4))
        with list_container.canvas.before:
            Color(0.12, 0.12, 0.12, 1)
            bg = Rectangle(pos=list_container.pos, size=list_container.size)
        with list_container.canvas.after:
            Color(0.5, 0.5, 0.5, 1)
            border = Line(rectangle=(*list_container.pos, *list_container.size), width=1.2)

        def upd(*_):
            bg.pos = list_container.pos
            bg.size = list_container.size
            border.rectangle = (*list_container.pos, *list_container.size)

        list_container.bind(pos=upd, size=upd)
        list_container.add_widget(list_scroll)
        box.add_widget(list_container)

        return box

    def refresh_senders_list(self):
        self.senders_list_layout.clear_widgets()
        for idx, s in enumerate(self.senders):
            email = s.get("email", "")
            row = SenderRow(
                text=email,
                on_delete=lambda i=idx: self.show_delete_confirm(
                    lambda: self.delete_sender(i)
                ),
            )
            self.senders_list_layout.add_widget(row)

    def refresh_recipients_list(self):
        self.recipients_list_layout.clear_widgets()
        for idx, email in enumerate(self.recipients):
            row = RecipientRow(
                text=email,
                on_delete=lambda i=idx: self.show_delete_confirm(
                    lambda: self.delete_recipient(i)
                ),
            )
            self.recipients_list_layout.add_widget(row)

    def show_sender_form_popup(self, edit_index=None):
        is_edit = edit_index is not None
        initial_email = self.senders[edit_index]["email"] if is_edit else ""
        initial_pw = self.senders[edit_index]["password"] if is_edit else ""

        wrapper = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(12),
        )

        wrapper.add_widget(
            Label(
                text="Email Address",
                size_hint_y=None,
                height=dp(28),
                halign="left",
                valign="middle",
            )
        )
        email_input = TextInput(
            text=initial_email,
            multiline=False,
            size_hint_y=None,
            height=dp(54),
            font_size="16sp",
            padding=[dp(8), dp(10), dp(8), dp(10)],
        )
        wrapper.add_widget(email_input)

        wrapper.add_widget(
            Label(
                text="App Password",
                size_hint_y=None,
                height=dp(28),
                halign="left",
                valign="middle",
            )
        )
        pw_input = TextInput(
            text=initial_pw,
            multiline=False,
            password=True,
            size_hint_y=None,
            height=dp(54),
            font_size="16sp",
            padding=[dp(8), dp(10), dp(8), dp(10)],
        )
        wrapper.add_widget(pw_input)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        save_btn = Button(text="Save", background_normal="", background_color=NORMAL_GREEN)
        cancel_btn = Button(text="Cancel", background_normal="", background_color=RED)
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        wrapper.add_widget(btn_row)

        popup = Popup(
            title="Edit Sender" if is_edit else "Add Sender",
            content=wrapper,
            size_hint=(0.92, None),
            height=dp(320),
            auto_dismiss=False,
        )

        def submit_and_close(*_):
            email = email_input.text.strip()
            password = pw_input.text.strip()
            if not email or not password:
                return
            if is_edit:
                self.senders[edit_index] = {"email": email, "password": password}
            else:
                self.senders.append({"email": email, "password": password})
            self.save_config()
            self.refresh_senders_list()
            popup.dismiss()

        save_btn.bind(on_release=submit_and_close)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def show_recipient_form_popup(self, edit_index=None):
        is_edit = edit_index is not None
        initial_email = self.recipients[edit_index] if is_edit else ""

        wrapper = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(12),
        )

        wrapper.add_widget(
            Label(
                text="Email Address",
                size_hint_y=None,
                height=dp(28),
                halign="left",
                valign="middle",
            )
        )
        email_input = TextInput(
            text=initial_email,
            multiline=False,
            size_hint_y=None,
            height=dp(54),
            font_size="16sp",
            padding=[dp(8), dp(10), dp(8), dp(10)],
        )
        wrapper.add_widget(email_input)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        save_btn = Button(text="Save", background_normal="", background_color=NORMAL_GREEN)
        cancel_btn = Button(text="Cancel", background_normal="", background_color=RED)
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        wrapper.add_widget(btn_row)

        popup = Popup(
            title="Edit Recipient" if is_edit else "Add Recipient",
            content=wrapper,
            size_hint=(0.92, None),
            height=dp(240),
            auto_dismiss=False,
        )

        def submit_and_close(*_):
            email = email_input.text.strip()
            if not email:
                return
            if is_edit:
                self.recipients[edit_index] = email
            else:
                self.recipients.append(email)
            self.save_config()
            self.refresh_recipients_list()
            popup.dismiss()

        save_btn.bind(on_release=submit_and_close)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def show_max_emails_popup(self):
        wrapper = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(12),
        )

        wrapper.add_widget(
            Label(
                text="Max emails",
                size_hint_y=None,
                height=dp(28),
                halign="left",
                valign="middle",
            )
        )
        num_input = TextInput(
            text=str(self.max_emails_value),
            multiline=False,
            input_filter="int",
            size_hint_y=None,
            height=dp(54),
            font_size="16sp",
            padding=[dp(8), dp(10), dp(8), dp(10)],
        )
        wrapper.add_widget(num_input)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        save_btn = Button(text="Save", background_normal="", background_color=NORMAL_GREEN)
        cancel_btn = Button(text="Cancel", background_normal="", background_color=RED)
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        wrapper.add_widget(btn_row)

        popup = Popup(
            title="Set Max Emails",
            content=wrapper,
            size_hint=(0.92, None),
            height=dp(240),
            auto_dismiss=False,
        )

        def submit_and_close(*_):
            raw = num_input.text.strip()
            try:
                val = int(raw) if raw else 20
            except ValueError:
                val = 20
            self.max_emails_value = val
            if hasattr(self, "max_emails_btn"):
                self.max_emails_btn.text = f"Max emails: {self.max_emails_value}"
            self.save_config()
            popup.dismiss()

        save_btn.bind(on_release=submit_and_close)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def delete_sender(self, idx):
        try:
            del self.senders[idx]
            self.save_config()
            self.refresh_senders_list()
        except Exception:
            pass

    def delete_recipient(self, idx):
        try:
            del self.recipients[idx]
            self.save_config()
            self.refresh_recipients_list()
        except Exception:
            pass

    def on_pause(self):
        return True

    # ---------------- CONFIG ----------------
    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.senders = data.get("senders", []) or []
                self.recipients = data.get("recipients", []) or []
                mr = data.get("max_emails", "")
                try:
                    self.max_emails_value = int(mr) if str(mr).strip() else 20
                except ValueError:
                    self.max_emails_value = 20
                if hasattr(self, "max_emails_btn"):
                    self.max_emails_btn.text = f"Max emails: {self.max_emails_value}"
        except Exception:
            self.senders = []
            self.recipients = []
            self.max_emails_value = 20
            if hasattr(self, "max_emails_btn"):
                self.max_emails_btn.text = f"Max emails: {self.max_emails_value}"

    def save_config(self):
        try:
            os.makedirs(self.user_data_dir, exist_ok=True)
            data = {
                "senders": self.senders,
                "recipients": self.recipients,
                "max_emails": str(self.max_emails_value),
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
        threading.Thread(target=func, daemon=True).start()

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

                unique_titles = []
                seen = set()
                for t, s in items:
                    if t not in seen:
                        unique_titles.append((t, s))
                        seen.add(t)

                sent_count = len(self.sent_titles)
                remaining_new = len([t for t, _ in unique_titles if t not in self.sent_titles])

                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(
                            f"RSS OK\n"
                            f"Total items: {len(unique_titles)}\n"
                            f"Sent items: {sent_count}\n"
                            f"remaining: {remaining_new}\n"
                            f"Elapsed time: {elapsed:.1f}s"
                        ),
                        self.set_buttons_enabled(True),
                    ),
                    0,
                )
            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(f"RSS Error:\n{e}\n\n{tb}"),
                        self.set_buttons_enabled(True),
                    ),
                    0,
                )

        self.run_in_thread(task)

    def on_send(self, *_):
        self.show_send_confirm()

    def do_send(self):
        if not self.senders:
            self.set_status("Please add at least one sender.")
            return
        if not self.recipients:
            self.set_status("Please add at least one recipient.")
            return

        max_emails = self.max_emails_value or 20

        to_emails = [x.strip() for x in self.recipients if str(x).strip()]
        self.set_buttons_enabled(False)
        self.set_status("Sending...")

        def task():
            try:
                items, total = collect_news_safe()

                unique_items = []
                seen = set()
                for t, s in items:
                    if t not in seen:
                        unique_items.append((t, s))
                        seen.add(t)

                new_items = [(t, s) for (t, s) in unique_items if t not in self.sent_titles]
                batch_items = new_items[:max_emails]

                if not batch_items:
                    Clock.schedule_once(
                        lambda dt: (
                            self.set_status("No new items to send."),
                            self.set_buttons_enabled(True),
                        ),
                        0,
                    )
                    return

                results = []
                success_count = 0
                sent_per_sender = {}

                for idx, s in enumerate(self.senders):
                    sender_email = s.get("email", "").strip()
                    app_pass = s.get("password", "").strip()

                    if not sender_email or not app_pass:
                        results.append(f"{sender_email or 'Unknown'}: skipped (missing data)")
                        sent_per_sender[sender_email or "Unknown"] = 0
                        continue

                    def progress_cb(cur, tot, se=sender_email):
                        Clock.schedule_once(
                            lambda dt, _se=se, _c=cur, _t=tot: self.set_status(
                                f"Sending...\n{_se}\nEmail {_c}/{_t}"
                            ),
                            0,
                        )

                    ok, msg = send_emails_safe(
                        sender_email, app_pass, to_emails, batch_items, progress_cb=progress_cb
                    )

                    if ok:
                        success_count += 1
                        results.append(f"{sender_email}: OK ({len(batch_items)} items)")
                        sent_per_sender[sender_email] = len(batch_items)
                    else:
                        results.append(f"{sender_email}: FAIL ({msg})")
                        sent_per_sender[sender_email] = 0

                    if idx < len(self.senders) - 1:
                        time.sleep(random.uniform(*SENDER_DELAY_RANGE))

                if success_count > 0:
                    sent_now_titles = [t for t, _ in batch_items]
                    append_sent_titles(self.sent_titles_path, sent_now_titles)
                    self.sent_titles.update(sent_now_titles)

                remaining_after = len([t for t, _ in new_items if t not in set(t for t, _ in batch_items)])

                out = (
                    "Finished.\n"
                    f"Batch sent: {len(batch_items)}\n"
                    f"Successful senders: {success_count}/{len(self.senders)}\n"
                    f"Sent feeds total: {len(self.sent_titles)}\n"
                    f"Remaining feeds total: {remaining_after}\n\n"
                    + "\n".join(results)
                )

                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(out),
                        self.set_buttons_enabled(True),
                    ),
                    0,
                )

            except Exception as e:
                tb = traceback.format_exc()
                Clock.schedule_once(
                    lambda dt: (
                        self.set_status(f"Error:\n{e}\n\n{tb}"),
                        self.set_buttons_enabled(True),
                    ),
                    0,
                )

        self.run_in_thread(task)


if __name__ == "__main__":
    NewsApp().run()
