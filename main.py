import os
import json
import threading
import time

import feedparser

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.modalview import ModalView
from kivy.clock import Clock
from kivy.core.window import Window


RSS_FEEDS = [
    "https://feeds.bbci.co.uk/persian/rss.xml",
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
    "https://www.parseek.com/rss/",
]


def load_sent_titles(filename: str) -> set:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        return set(line for line in lines if line)
    except FileNotFoundError:
        return set()


def append_sent_titles(filename: str, titles: list) -> None:
    if not titles:
        return
    with open(filename, "a", encoding="utf-8") as f:
        for title in titles:
            safe_title = title.replace("\n", " ")
            f.write(safe_title + "\n")


def collect_news() -> list:
    all_items = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "").strip()
            if not title:
                continue
            if not summary:
                summary = title
            all_items.append((title, summary))
    return all_items


class NewsApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_file = None
        self.sent_file = None
        self.pin_file = None
        self.stats_file = None
        self.stored_pin = None

        self.total_sent = 0
        self.senders = []

        self.senders_layout = None
        self.recipients_layout = None
        self.recipient_inputs = []
        self.max_emails_input = None
        self.status_label = None
        self.total_label = None
        self.send_button = None

        self.login_view = None
        self.login_status_label = None
        self.pin_input = None

        self.loading_view = None
        self.loading_label = None

        self.sender_modal = None
        self.sender_modal_title = None
        self.sender_email_input = None
        self.sender_password_input = None
        self.editing_sender_index = None

        self.menu_view = None
        self.last_back_press_time = 0.0

    def build(self):
        Window.clearcolor = (0.95, 0.97, 0.99, 1)

        root = BoxLayout(orientation="vertical", padding=16, spacing=10)

        top_bar = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40, spacing=8)

        menu_button = Button(
            text="≡",
            size_hint=(None, 1),
            width=50,
            background_normal="",
            background_color=(0.8, 0.8, 0.8, 1),
        )
        menu_button.bind(on_press=self.on_menu_pressed)

        title_label = Label(text="News Mailer", font_size="20sp", size_hint=(1, 1))

        top_bar.add_widget(menu_button)
        top_bar.add_widget(title_label)

        senders_title = Label(text="Sender emails", size_hint=(1, None), height=30)

        self.senders_layout = BoxLayout(orientation="vertical", spacing=5, size_hint=(1, None))
        self.senders_layout.bind(minimum_height=self.senders_layout.setter("height"))

        add_sender_btn = Button(
            text="Add sender email",
            size_hint=(1, None),
            height=40,
            background_normal="",
            background_color=(0.2, 0.5, 0.8, 1),
        )
        add_sender_btn.bind(on_press=self.on_add_sender_pressed)

        recipients_title = Label(text="Recipients", size_hint=(1, None), height=30)

        self.recipients_layout = BoxLayout(orientation="vertical", spacing=5, size_hint=(1, None))
        self.recipients_layout.bind(minimum_height=self.recipients_layout.setter("height"))
        self.recipient_inputs = []

        add_recipient_btn = Button(
            text="Add recipient",
            size_hint=(1, None),
            height=40,
            background_normal="",
            background_color=(0.2, 0.5, 0.8, 1),
        )
        add_recipient_btn.bind(on_press=self.on_add_recipient)

        self.max_emails_input = TextInput(
            hint_text="Max emails per send (e.g. 2, 10, 20)",
            multiline=False,
            input_filter="int",
            size_hint=(1, None),
            height=40,
        )

        save_button = Button(
            text="Save",
            size_hint=(1, None),
            height=45,
            background_normal="",
            background_color=(0.1, 0.6, 0.5, 1),
        )
        save_button.bind(on_press=self.on_save_pressed)

        self.send_button = Button(
            text="Send (TEST MODE)",
            size_hint=(1, None),
            height=50,
            background_normal="",
            background_color=(0.2, 0.4, 0.8, 1),
        )
        self.send_button.bind(on_press=self.on_send_pressed)

        self.total_label = Label(text="Total emails sent: 0", size_hint=(1, None), height=30)

        self.status_label = Label(
            text="Test build. App should open without crash.",
            size_hint=(1, None),
            height=40,
        )

        root.add_widget(top_bar)
        root.add_widget(senders_title)
        root.add_widget(self.senders_layout)
        root.add_widget(add_sender_btn)
        root.add_widget(recipients_title)
        root.add_widget(self.recipients_layout)
        root.add_widget(add_recipient_btn)
        root.add_widget(self.max_emails_input)
        root.add_widget(save_button)
        root.add_widget(self.send_button)
        root.add_widget(self.total_label)
        root.add_widget(self.status_label)

        self.create_login_view()
        self.create_loading_view()
        self.create_sender_modal()
        self.create_menu_view()

        Window.bind(on_keyboard=self.on_keyboard)

        return root

    def on_start(self):
        self.config_file = os.path.join(self.user_data_dir, "config.json")
        self.sent_file = os.path.join(self.user_data_dir, "sent_titles.txt")
        self.pin_file = os.path.join(self.user_data_dir, "pin.json")
        self.stats_file = os.path.join(self.user_data_dir, "stats.json")

        self.load_config()
        Clock.schedule_once(lambda dt: self.login_view.open(), 0)

    def on_keyboard(self, window, key, scancode, codepoint, modifiers):
        if key == 27:
            return self.handle_back_button()
        return False

    def handle_back_button(self):
        now = time.time()
        if now - self.last_back_press_time < 1.5:
            App.get_running_app().stop()
        else:
            self.last_back_press_time = now
            self.status_label.text = "Press back again to exit."
        return True

    def create_login_view(self):
        self.login_view = ModalView(size_hint=(1, 1), auto_dismiss=False)
        layout = BoxLayout(orientation="vertical", padding=30, spacing=15)

        title = Label(text="Secure Access", font_size="22sp", size_hint=(1, None), height=40)
        subtitle = Label(text="Enter 4-digit PIN", size_hint=(1, None), height=30)

        self.pin_input = TextInput(
            hint_text="4-digit PIN",
            multiline=False,
            password=True,
            input_filter="int",
            size_hint=(1, None),
            height=40,
        )

        unlock_btn = Button(
            text="Unlock",
            size_hint=(1, None),
            height=45,
            background_normal="",
            background_color=(0.2, 0.5, 0.8, 1),
        )
        unlock_btn.bind(on_press=lambda x: self.login_view.dismiss())

        layout.add_widget(title)
        layout.add_widget(subtitle)
        layout.add_widget(self.pin_input)
        layout.add_widget(unlock_btn)

        self.login_view.add_widget(layout)

    def create_loading_view(self):
        self.loading_view = ModalView(size_hint=(0.6, 0.25), auto_dismiss=False)
        inner = BoxLayout(orientation="vertical", padding=20, spacing=10)
        self.loading_label = Label(text="Please wait", size_hint=(1, None), height=30)
        inner.add_widget(Label(text="Sending...", font_size="18sp", size_hint=(1, None), height=30))
        inner.add_widget(self.loading_label)
        self.loading_view.add_widget(inner)

    def show_loading(self, message="Sending..."):
        self.loading_label.text = message
        if not self.loading_view.parent:
            self.loading_view.open()

    def hide_loading(self):
        if self.loading_view.parent:
            self.loading_view.dismiss()

    def create_menu_view(self):
        self.menu_view = ModalView(size_hint=(0.6, 0.5), auto_dismiss=True)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)
        layout.add_widget(Label(text="Menu", font_size="18sp", size_hint=(1, None), height=30))
        close_btn = Button(text="Close", size_hint=(1, None), height=40)
        close_btn.bind(on_press=lambda instance: self.menu_view.dismiss())
        layout.add_widget(close_btn)
        self.menu_view.add_widget(layout)

    def on_menu_pressed(self, instance):
        self.menu_view.open()

    def create_sender_modal(self):
        self.sender_modal = ModalView(size_hint=(0.9, 0.5), auto_dismiss=True)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)
        self.sender_modal_title = Label(text="Add sender email", font_size="18sp", size_hint=(1, None), height=30)

        self.sender_email_input = TextInput(hint_text="Sender email (Gmail)", multiline=False, size_hint=(1, None), height=40)
        self.sender_password_input = TextInput(hint_text="App Password (16 chars)", multiline=False, password=True, size_hint=(1, None), height=40)

        save_btn = Button(text="Save", size_hint=(1, None), height=45)
        save_btn.bind(on_press=self.on_sender_save)

        layout.add_widget(self.sender_modal_title)
        layout.add_widget(self.sender_email_input)
        layout.add_widget(self.sender_password_input)
        layout.add_widget(save_btn)

        self.sender_modal.add_widget(layout)

    def on_add_sender_pressed(self, instance):
        self.sender_email_input.text = ""
        self.sender_password_input.text = ""
        self.sender_modal.open()

    def on_sender_save(self, instance):
        email = self.sender_email_input.text.strip()
        password = self.sender_password_input.text.strip()
        if email and password:
            self.senders.append({"email": email, "password": password})
        self.sender_modal.dismiss()
        self.update_senders_ui()
        self.save_config()

    def update_senders_ui(self):
        self.senders_layout.clear_widgets()
        for s in self.senders:
            self.senders_layout.add_widget(Label(text=s["email"], size_hint=(1, None), height=30))

    def on_add_recipient(self, instance=None, initial_value=""):
        row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40, spacing=5)
        inp = TextInput(text=initial_value, hint_text="Recipient email", multiline=False)
        row.add_widget(inp)
        self.recipients_layout.add_widget(row)
        self.recipient_inputs.append(inp)

    def get_recipients_from_ui(self):
        return [inp.text.strip() for inp in self.recipient_inputs if inp.text.strip()]

    def get_config_from_ui(self):
        max_emails = int(self.max_emails_input.text.strip() or "2")
        return {"senders": self.senders, "recipients": self.get_recipients_from_ui(), "max_emails": max_emails}

    def save_config(self):
        cfg = self.get_config_from_ui()
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_config(self):
        if not self.config_file or not os.path.exists(self.config_file):
            self.on_add_recipient()
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.senders = cfg.get("senders", [])
            self.update_senders_ui()
            self.max_emails_input.text = str(cfg.get("max_emails", 2))
            for r in cfg.get("recipients", []) or [""]:
                self.on_add_recipient(initial_value=r)
        except:
            self.on_add_recipient()

    # --------- TEST SEND (NO NETWORK) ---------
    def on_save_pressed(self, instance):
        self.save_config()
        self.status_label.text = "Saved."

    def on_send_pressed(self, instance):
        self.send_button.disabled = True
        self.show_loading("TEST: no network call")
        Clock.schedule_once(self.fake_send_done, 1.5)

    def fake_send_done(self, dt):
        self.hide_loading()
        self.status_label.text = "TEST OK. App did not crash."
        self.send_button.disabled = False


if __name__ == "__main__":
    NewsApp().run()
