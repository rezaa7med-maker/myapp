import os
import json
import time
import threading
import traceback
import ssl
import smtplib
import base64

import feedparser
import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.utils import get_color_from_hex


# ------------------------------------------------------------
# Safe crash logger (very important on Android)
# ------------------------------------------------------------
def write_crash(app_dir, text):
    try:
        downloads = "/sdcard/Download"
        os.makedirs(downloads, exist_ok=True)
        path = os.path.join(downloads, "crash.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def safe_call(app, where, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        tb = traceback.format_exc()
        try:
            app_dir = app.user_data_dir
        except Exception:
            app_dir = "/sdcard"
        write_crash(app_dir, f"[{where}]\n{tb}")

        # show on UI if possible
        try:
            if hasattr(app, "show_info"):
                Clock.schedule_once(
                    lambda *_: app.show_info("CRASH", f"{where}\n\n{e}\n\n{tb}"), 0
                )
        except Exception:
            pass
        raise


# ------------------------------------------------------------
# Fix for base64 old calls
# ------------------------------------------------------------
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes
if not hasattr(base64, "encodestring"):
    base64.encodestring = base64.encodebytes


APP_TITLE = "News Mailer (Safe Boot)"

DEFAULT_MAX_EMAILS = 20
DEFAULT_DELAY_SECONDS = 4

RSS_FEEDS = [
    {
        "name": "Mehr News",
        "url": "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
        "site_url": "https://www.mehrnews.com/",
    },
    {
        "name": "Tabnak",
        "url": "https://www.tabnak.ir/fa/rss/allnews",
        "site_url": "https://www.tabnak.ir/",
    },
    {
        "name": "Euronews Farsi",
        "url": "https://parsi.euronews.com/index.php/rss?level=program&name=world",
        "site_url": "https://parsi.euronews.com/",
    },
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}


# --------------------- Storage helpers ---------------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_sent_titles(path):
    if not os.path.exists(path):
        return set()
    titles = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if t:
                    titles.add(t)
    except Exception:
        pass
    return titles


def append_sent_titles(path, titles):
    if not titles:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for t in titles:
                f.write(t.replace("\n", " ").strip() + "\n")
    except Exception:
        pass


def reset_sent_titles_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# --------------------- RSS helpers ---------------------
def strip_html(text):
    if not text:
        return ""
    return (
        text.replace("<br>", "\n")
            .replace("<br/>", "\n")
            .replace("<br />", "\n")
    )


def summarize_entry(entry, max_chars=600):
    summary = ""
    if "summary" in entry:
        summary = strip_html(entry.summary)
    elif "description" in entry:
        summary = strip_html(entry.description)
    summary = " ".join(summary.split())
    if len(summary) > max_chars:
        summary = summary[: max_chars - 3].rstrip() + "..."
    return summary


def normalize_title(t):
    return " ".join((t or "").split()).strip()


def fetch_all_feed_items():
    items = []
    total_entries = 0

    for feed in RSS_FEEDS:
        try:
            r = requests.get(feed["url"], headers=REQUEST_HEADERS, timeout=12)
            r.raise_for_status()

            parsed = feedparser.parse(r.text)
            entries = getattr(parsed, "entries", []) or []
            total_entries += len(entries)

            for entry in entries:
                title = normalize_title(getattr(entry, "title", ""))
                if not title:
                    continue
                summary = summarize_entry(entry)
                items.append({
                    "title": title,
                    "summary": summary or title,
                    "site_url": feed["site_url"],
                    "published": getattr(entry, "published", "") or getattr(entry, "updated", ""),
                })
        except Exception:
            continue

    items.sort(key=lambda x: x.get("published", ""), reverse=True)
    return items, total_entries


# --------------------- Email sending ---------------------
def send_one_sender_batch(sender_email, app_password, recipients, batch_items, delay_seconds, log_func):
    new_titles = set()
    last_err = None

    for verified in (True, False):
        try:
            context = ssl.create_default_context() if verified else ssl._create_unverified_context()

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=20) as server:
                server.login(sender_email, app_password)

                for item in batch_items:
                    title = item["title"]
                    summary = item["summary"]
                    site_url = item["site_url"]

                    msg = "\n".join([
                        f"To: {', '.join(recipients)}",
                        f"Subject: {title}",
                        "",
                        f"{summary}\n\nSource: {site_url}",
                    ])

                    try:
                        server.sendmail(sender_email, recipients, msg.encode("utf-8"))
                        new_titles.add(title)
                        log_func(f"Sent: {title}")
                    except Exception as e:
                        log_func(f"[Send Error] {title}: {e}")

                    time.sleep(delay_seconds)

            log_func("Sender finished." + (" (verified SSL)" if verified else " (unverified SSL)"))
            return new_titles

        except Exception as e:
            last_err = e
            if verified and "CERTIFICATE_VERIFY_FAILED" in str(e):
                log_func("SSL verify failed, retrying without verification...")
                continue
            break

    log_func(f"[Sender Error] {sender_email}: {last_err}")
    return new_titles


# --------------------- UI widgets ---------------------
class ListRow(BoxLayout):
    text = StringProperty("")
    on_edit = ObjectProperty(None)
    on_delete = ObjectProperty(None)

    def __init__(self, text="", on_edit=None, on_delete=None, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(6),
            **kwargs
        )
        self.text = text
        self.on_edit = on_edit
        self.on_delete = on_delete

        self.lbl = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_x=0.78,
            font_size="15sp"
        )
        self.lbl.bind(size=self._refresh_text_size)

        btn_edit = Button(text="Edit", size_hint_x=0.11, font_size="14sp")
        btn_del = Button(text="Delete", size_hint_x=0.11, font_size="14sp")

        btn_edit.bind(on_release=lambda *_: self.on_edit() if self.on_edit else None)
        btn_del.bind(on_release=lambda *_: self.on_delete() if self.on_delete else None)

        self.add_widget(self.lbl)
        self.add_widget(btn_edit)
        self.add_widget(btn_del)

    def _refresh_text_size(self, *_):
        self.lbl.text_size = (self.lbl.width, None)


# --------------------- Main App ---------------------
class NewsMailerApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.senders = []
        self.recipients = []
        self.sent_titles = set()

        self.max_emails = DEFAULT_MAX_EMAILS
        self.delay_seconds = DEFAULT_DELAY_SECONDS

        self.is_sending = False

        self.senders_list_layout = None
        self.recipients_list_layout = None
        self.total_sent_label = None
        self.remaining_label = None

        self.sending_popup = None
        self.sending_list_layout = None
        self.sending_close_btn = None

    def build(self):
        # wrap everything build does
        return safe_call(self, "build()", self._build_impl)

    def _build_impl(self):
        self.title = APP_TITLE
        Window.clearcolor = get_color_from_hex("#0F1115")

        self.data_dir = self.user_data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self.senders_path = os.path.join(self.data_dir, "senders.json")
        self.recipients_path = os.path.join(self.data_dir, "recipients.json")
        self.sent_titles_path = os.path.join(self.data_dir, "sent_titles.txt")

        self.load_state()

        root = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(8), dp(8), dp(8), dp(8)],
            spacing=dp(8),
        )
        title_lbl = Label(
            text=APP_TITLE,
            bold=True,
            font_size="20sp",
            halign="left",
            valign="middle",
        )
        title_lbl.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, None)))

        menu_btn = Button(
            text="≡",
            size_hint=(None, None),
            size=(dp(48), dp(48)),
            font_size="20sp",
        )
        menu_btn.bind(on_release=self.open_menu)

        header.add_widget(title_lbl)
        header.add_widget(menu_btn)
        root.add_widget(self._card(header))

        status = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            padding=[dp(6), 0, dp(6), 0],
        )
        self.total_sent_label = Label(text="Total Sent: 0", halign="left", font_size="14sp")
        self.remaining_label = Label(text="Remaining: 0", halign="right", font_size="14sp")
        status.add_widget(self.total_sent_label)
        status.add_widget(self.remaining_label)
        root.add_widget(self._card(status))

        settings = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
            padding=[dp(6), dp(6), dp(6), dp(6)],
        )

        settings.add_widget(Label(text="Max Emails", size_hint_x=0.32, font_size="14sp"))
        self.max_emails_input = TextInput(
            text=str(self.max_emails),
            multiline=False,
            input_filter="int",
            size_hint_x=0.18,
            font_size="15sp",
            padding=[dp(8), dp(12)],
        )
        settings.add_widget(self.max_emails_input)

        settings.add_widget(Label(text="Delay (sec)", size_hint_x=0.30, font_size="14sp"))
        self.delay_input = TextInput(
            text=str(self.delay_seconds),
            multiline=False,
            input_filter="int",
            size_hint_x=0.12,
            font_size="15sp",
            padding=[dp(8), dp(12)],
        )
        settings.add_widget(self.delay_input)

        root.add_widget(self._card(settings))

        boxes_holder = BoxLayout(orientation="vertical", spacing=dp(10))

        def rebuild_boxes(*_):
            boxes_holder.clear_widgets()
            if Window.width < dp(700):
                boxes_holder.add_widget(self._build_senders_box())
                boxes_holder.add_widget(self._build_recipients_box())
            else:
                two_cols = BoxLayout(orientation="horizontal", spacing=dp(10))
                two_cols.add_widget(self._build_senders_box())
                two_cols.add_widget(self._build_recipients_box())
                boxes_holder.add_widget(two_cols)

        Window.bind(size=lambda *_: rebuild_boxes())
        rebuild_boxes()
        root.add_widget(boxes_holder)

        btn_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
        )
        test_btn = Button(text="Test RSS", font_size="18sp")
        send_btn = Button(text="Send", font_size="18sp")

        test_btn.bind(on_release=self.on_test_rss)
        send_btn.bind(on_release=self.confirm_send)

        btn_row.add_widget(test_btn)
        btn_row.add_widget(send_btn)
        root.add_widget(btn_row)

        self.refresh_lists()
        self.refresh_counters_async()

        self.root = root
        return root

    def _card(self, widget):
        wrapper = BoxLayout(orientation="vertical", padding=dp(6), size_hint_y=None)
        wrapper.add_widget(widget)
        wrapper.height = widget.height + dp(12)
        return wrapper

    # ---------------- Menu / Reset / Exit ----------------
    def open_menu(self, *_):
        safe_call(self, "open_menu()", self._open_menu_impl)

    def _open_menu_impl(self):
        dropdown = DropDown()
        reset_btn = Button(text="Reset Sent Log", size_hint_y=None, height=dp(44))
        exit_btn = Button(text="Exit", size_hint_y=None, height=dp(44))

        reset_btn.bind(on_release=lambda *_: (dropdown.dismiss(), self.confirm_reset()))
        exit_btn.bind(on_release=lambda *_: (dropdown.dismiss(), self.stop()))

        dropdown.add_widget(reset_btn)
        dropdown.add_widget(exit_btn)
        dropdown.open(self.root)

    def confirm_reset(self):
        self.show_confirm(
            "Are you sure?",
            "This will clear the sent titles log.",
            "Yes",
            "No",
            self.do_reset,
        )

    def do_reset(self):
        reset_sent_titles_file(self.sent_titles_path)
        self.sent_titles = set()
        self.update_total_sent()
        self.refresh_counters_async()

    # ---------------- State ----------------
    def load_state(self):
        self.senders = load_json(self.senders_path, [])
        self.recipients = load_json(self.recipients_path, [])
        self.sent_titles = load_sent_titles(self.sent_titles_path)
        self.update_total_sent()

    def save_state(self):
        save_json(self.senders_path, self.senders)
        save_json(self.recipients_path, self.recipients)

    def on_stop(self):
        self.save_state()

    # ---------------- Lists UI ----------------
    def refresh_lists(self):
        if self.senders_list_layout:
            self.senders_list_layout.clear_widgets()
            for idx, s in enumerate(self.senders):
                email = s.get("email", "")
                row = ListRow(
                    text=email,
                    on_edit=lambda i=idx: self.show_edit_sender_popup(i),
                    on_delete=lambda i=idx: self.confirm_delete_sender(i),
                )
                self.senders_list_layout.add_widget(row)

        if self.recipients_list_layout:
            self.recipients_list_layout.clear_widgets()
            for idx, r in enumerate(self.recipients):
                row = ListRow(
                    text=r,
                    on_edit=lambda i=idx: self.show_edit_recipient_popup(i),
                    on_delete=lambda i=idx: self.confirm_delete_recipient(i),
                )
                self.recipients_list_layout.add_widget(row)

    def _build_senders_box(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        box.add_widget(Label(text="Senders", bold=True, size_hint_y=None, height=dp(26), font_size="16sp"))

        self.senders_list_layout = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.senders_list_layout.bind(minimum_height=self.senders_list_layout.setter("height"))

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.senders_list_layout)
        box.add_widget(scroll)

        add_btn = Button(text="Add Sender", size_hint_y=None, height=dp(44), font_size="16sp")
        add_btn.bind(on_release=self.show_add_sender_popup)
        box.add_widget(add_btn)

        return self._card(box)

    def _build_recipients_box(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        box.add_widget(Label(text="Recipients", bold=True, size_hint_y=None, height=dp(26), font_size="16sp"))

        self.recipients_list_layout = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.recipients_list_layout.bind(minimum_height=self.recipients_list_layout.setter("height"))

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.recipients_list_layout)
        box.add_widget(scroll)

        add_btn = Button(text="Add Recipient", size_hint_y=None, height=dp(44), font_size="16sp")
        add_btn.bind(on_release=self.show_add_recipient_popup)
        box.add_widget(add_btn)

        return self._card(box)

    # ---------------- Popups: Senders ----------------
    def show_add_sender_popup(self, *_):
        self.show_sender_form_popup("Add Sender", self.add_sender)

    def show_edit_sender_popup(self, idx):
        sender = self.senders[idx]
        self.show_sender_form_popup(
            "Edit Sender",
            lambda email, pw: self.edit_sender(idx, email, pw),
            initial_email=sender.get("email", ""),
            initial_password=sender.get("password", ""),
        )

    def show_sender_form_popup(self, title, on_submit, initial_email="", initial_password=""):
        layout = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(Label(text="Email Address"))
        email_input = TextInput(text=initial_email, multiline=False)
        layout.add_widget(email_input)

        layout.add_widget(Label(text="App Password"))
        pw_input = TextInput(text=initial_password, multiline=False, password=True)
        layout.add_widget(pw_input)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
        ok_btn = Button(text="OK")
        cancel_btn = Button(text="Cancel")

        popup = Popup(title=title, content=BoxLayout(orientation="vertical"), size_hint=(0.9, None), height=dp(260))
        popup.content.add_widget(layout)
        popup.content.add_widget(btn_row)

        def submit_and_close(*_):
            email = email_input.text.strip()
            password = pw_input.text.strip()
            if not email or not password:
                self.show_info("Invalid Input", "Email and App Password are required.")
                return
            on_submit(email, password)
            popup.dismiss()

        ok_btn.bind(on_release=submit_and_close)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        btn_row.add_widget(ok_btn)
        btn_row.add_widget(cancel_btn)

        popup.open()

    def add_sender(self, email, password):
        self.senders.append({"email": email, "password": password})
        self.save_state()
        self.refresh_lists()

    def edit_sender(self, idx, email, password):
        self.senders[idx] = {"email": email, "password": password}
        self.save_state()
        self.refresh_lists()

    def confirm_delete_sender(self, idx):
        self.show_confirm(
            "Delete Sender?",
            "Delete this sender?",
            "Yes",
            "No",
            lambda: self.delete_sender(idx),
        )

    def delete_sender(self, idx):
        del self.senders[idx]
        self.save_state()
        self.refresh_lists()

    # ---------------- Popups: Recipients ----------------
    def show_add_recipient_popup(self, *_):
        self.show_recipient_form_popup("Add Recipient", self.add_recipient)

    def show_edit_recipient_popup(self, idx):
        self.show_recipient_form_popup(
            "Edit Recipient",
            lambda email: self.edit_recipient(idx, email),
            initial_email=self.recipients[idx],
        )

    def show_recipient_form_popup(self, title, on_submit, initial_email=""):
        layout = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))

        layout.add_widget(Label(text="Email Address"))
        email_input = TextInput(text=initial_email, multiline=False)
        layout.add_widget(email_input)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
        ok_btn = Button(text="OK")
        cancel_btn = Button(text="Cancel")

        popup = Popup(title=title, content=BoxLayout(orientation="vertical"), size_hint=(0.9, None), height=dp(200))
        popup.content.add_widget(layout)
        popup.content.add_widget(btn_row)

        def submit_and_close(*_):
            email = email_input.text.strip()
            if not email:
                self.show_info("Invalid Input", "Email is required.")
                return
            on_submit(email)
            popup.dismiss()

        ok_btn.bind(on_release=submit_and_close)
        cancel_btn.bind(on_release=lambda *_: popup.dismiss())
        btn_row.add_widget(ok_btn)
        btn_row.add_widget(cancel_btn)

        popup.open()

    def add_recipient(self, email):
        self.recipients.append(email)
        self.save_state()
        self.refresh_lists()

    def edit_recipient(self, idx, email):
        self.recipients[idx] = email
        self.save_state()
        self.refresh_lists()

    def confirm_delete_recipient(self, idx):
        self.show_confirm(
            "Delete Recipient?",
            "Delete this recipient?",
            "Yes",
            "No",
            lambda: self.delete_recipient(idx),
        )

    def delete_recipient(self, idx):
        del self.recipients[idx]
        self.save_state()
        self.refresh_lists()

    # ---------------- Generic popups ----------------
    def show_confirm(self, title, message, yes_text, no_text, on_yes):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        content.add_widget(Label(text=message))

        btns = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
        yes_btn = Button(text=yes_text)
        no_btn = Button(text=no_text)
        btns.add_widget(yes_btn)
        btns.add_widget(no_btn)
        content.add_widget(btns)

        popup = Popup(title=title, content=content, size_hint=(0.85, None), height=dp(200))

        yes_btn.bind(on_release=lambda *_: (popup.dismiss(), on_yes()))
        no_btn.bind(on_release=lambda *_: popup.dismiss())

        popup.open()

    def show_info(self, title, message):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        content.add_widget(Label(text=message))

        close_btn = Button(text="Close", size_hint_y=None, height=dp(44))
        content.add_widget(close_btn)

        popup = Popup(title=title, content=content, size_hint=(0.85, None), height=dp(210))
        close_btn.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    # ---------------- Counters ----------------
    def update_total_sent(self):
        if self.total_sent_label:
            self.total_sent_label.text = f"Total Sent: {len(self.sent_titles)}"

    def refresh_counters_async(self):
        def worker():
            remaining = self.count_remaining_items()
            Clock.schedule_once(lambda *_: self.set_remaining(remaining), 0)

        threading.Thread(target=worker, daemon=True).start()

    def set_remaining(self, remaining):
        if self.remaining_label:
            self.remaining_label.text = f"Remaining: {remaining}"

    def count_remaining_items(self):
        items, _ = fetch_all_feed_items()
        unique_items = [it for it in items if it["title"] not in self.sent_titles]
        return len(unique_items)

    # ---------------- Actions ----------------
    def on_test_rss(self, *_):
        def worker():
            try:
                items, total = fetch_all_feed_items()
                msg = f"RSS OK\nTotal entries: {total}\nCollected items: {len(items)}"
            except Exception as e:
                msg = f"RSS Error:\n{e}\n\n{traceback.format_exc()}"
            Clock.schedule_once(lambda *_: self.show_info("RSS Test", msg), 0)

        threading.Thread(target=worker, daemon=True).start()

    def confirm_send(self, *_):
        if self.is_sending:
            self.show_info("Busy", "Sending is already in progress.")
            return

        try:
            self.max_emails = int(self.max_emails_input.text.strip() or DEFAULT_MAX_EMAILS)
        except ValueError:
            self.max_emails = DEFAULT_MAX_EMAILS
        self.max_emails_input.text = str(self.max_emails)

        try:
            self.delay_seconds = int(self.delay_input.text.strip() or DEFAULT_DELAY_SECONDS)
        except ValueError:
            self.delay_seconds = DEFAULT_DELAY_SECONDS
        self.delay_input.text = str(self.delay_seconds)

        if not self.senders:
            self.show_info("Missing Senders", "Please add at least one sender.")
            return
        if not self.recipients:
            self.show_info("Missing Recipients", "Please add at least one recipient.")
            return

        self.show_confirm(
            "Are you sure?",
            "Start sending emails now?",
            "Yes",
            "No",
            self.start_sending,
        )

    def start_sending(self):
        self.is_sending = True
        self.open_sending_popup()
        threading.Thread(target=self.sending_worker, daemon=True).start()

    # ---------------- Sending Popup ----------------
    def open_sending_popup(self):
        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))

        header = Label(text="Sending...", size_hint_y=None, height=dp(28), bold=True)
        content.add_widget(header)

        scroll = ScrollView()
        self.sending_list_layout = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.sending_list_layout.bind(minimum_height=self.sending_list_layout.setter("height"))
        scroll.add_widget(self.sending_list_layout)
        content.add_widget(scroll)

        footer = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44))
        self.sending_close_btn = Button(text="Close", disabled=True)
        footer.add_widget(self.sending_close_btn)
        content.add_widget(footer)

        self.sending_popup = Popup(title="Sending...", content=content, size_hint=(0.9, 0.85))
        self.sending_close_btn.bind(on_release=lambda *_: self.sending_popup.dismiss())
        self.sending_popup.open()

    def log_sending_line(self, text):
        def add_line(*_):
            lbl = Label(text=text, halign="left", valign="middle", size_hint_y=None, height=dp(28))
            lbl.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, None)))
            self.sending_list_layout.add_widget(lbl)

        Clock.schedule_once(add_line, 0)

    def finish_sending_popup(self):
        def finalize(*_):
            self.log_sending_line("Done.")
            self.sending_popup.title = "Done"
            self.sending_close_btn.disabled = False

        Clock.schedule_once(finalize, 0)

    # ---------------- Sending worker ----------------
    def get_next_batch_items(self, n):
        all_items, _ = fetch_all_feed_items()
        batch = []
        for it in all_items:
            if it["title"] in self.sent_titles:
                continue
            batch.append(it)
            if len(batch) >= n:
                break
        return batch

    def sending_worker(self):
        try:
            batch_items = self.get_next_batch_items(self.max_emails)

            if not batch_items:
                self.log_sending_line("No new items to send.")
                self.finish_sending_popup()
                return

            new_titles = set()

            for sender in self.senders:
                sender_email = sender["email"]
                sender_pw = sender["password"]

                self.log_sending_line(f"Using sender: {sender_email}")
                sent_now = send_one_sender_batch(
                    sender_email,
                    sender_pw,
                    self.recipients,
                    batch_items,
                    self.delay_seconds,
                    self.log_sending_line,
                )
                new_titles.update(sent_now)

            if new_titles:
                append_sent_titles(self.sent_titles_path, new_titles)
                self.sent_titles.update(new_titles)
                self.log_sending_line(f"New items sent: {len(new_titles)}")
            else:
                self.log_sending_line("No items were sent successfully.")

            Clock.schedule_once(lambda *_: self.update_total_sent(), 0)
            self.refresh_counters_async()
            self.finish_sending_popup()

        finally:
            self.is_sending = False


if __name__ == "__main__":
    try:
        NewsMailerApp().run()
    except Exception:
        tb = traceback.format_exc()
        try:
            os.makedirs("/sdcard", exist_ok=True)
            with open("/sdcard/crash.txt", "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        raise
