import os
import json
import threading
import ssl
import smtplib
import time
import sys
import traceback
import logging

import feedparser

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.modalview import ModalView
from kivy.clock import Clock
from kivy.core.window import Window


# --------- CONSTANT DATA ---------
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/persian/rss.xml",
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
    "https://www.parseek.com/rss/",
]


# --------- LOGGING SETUP ---------
def setup_logging(log_path: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    def handle_exception(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical("UNCAUGHT EXCEPTION:\n%s", tb_text)

    sys.excepthook = handle_exception
    logging.info("Logging initialized. Log file: %s", log_path)


def log_exception(prefix="ERROR"):
    tb_text = traceback.format_exc()
    logging.error("%s:\n%s", prefix, tb_text)


# --------- UTILITY FUNCTIONS ---------
def load_sent_titles(filename: str) -> set:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
        return set(line for line in lines if line)
    except FileNotFoundError:
        return set()
    except Exception:
        log_exception("load_sent_titles failed")
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
        log_exception("append_sent_titles failed")


def collect_news() -> list:
    all_items = []
    try:
        for url in RSS_FEEDS:
            logging.info("Fetching RSS: %s", url)
            feed = feedparser.parse(url)

            for entry in feed.entries:
                title = getattr(entry, "title", "").strip()
                summary = getattr(entry, "summary", "").strip()
                if not title:
                    continue
                if not summary:
                    summary = title
                all_items.append((title, summary))
    except Exception:
        log_exception("collect_news failed")

    return all_items


def send_emails(sender_email, app_password, to_emails, news_items, log_func=print) -> None:
    try:
        context = ssl.create_default_context()

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)

            for title, summary in news_items:
                subject = title
                body = summary

                message_lines = [
                    f"To: {', '.join(to_emails)}",
                    f"Subject: {subject}",
                    "",
                    body,
                ]
                message = "\n".join(message_lines)

                server.sendmail(
                    sender_email,
                    to_emails,
                    message.encode("utf-8"),
                )

                log_func(f"Email sent from {sender_email}: {subject}")
                logging.info("Email sent from %s | subject=%s", sender_email, subject)

    except Exception:
        log_exception("send_emails failed")
        raise


# --------- MAIN APP ---------
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

        title_label = Label(
            text="News Mailer",
            font_size="20sp",
            size_hint=(1, 1),
        )

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
            text="Send",
            size_hint=(1, None),
            height=50,
            background_normal="",
            background_color=(0.2, 0.4, 0.8, 1),
        )
        self.send_button.bind(on_press=self.on_send_pressed)

        self.total_label = Label(text="Total emails sent: 0", size_hint=(1, None), height=30)

        self.status_label = Label(
            text="Add senders, recipients and max emails, then tap Send.",
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
        # setup log file first
        log_file = os.path.join(self.user_data_dir, "app.log")
        setup_logging(log_file)

        logging.info("App started.")

        self.config_file = os.path.join(self.user_data_dir, "config.json")
        self.sent_file = os.path.join(self.user_data_dir, "sent_titles.txt")
        self.pin_file = os.path.join(self.user_data_dir, "pin.json")
        self.stats_file = os.path.join(self.user_data_dir, "stats.json")

        self.load_config()
        self.load_pin()
        self.load_stats()
        self.update_total_label()

        Clock.schedule_once(lambda dt: self.login_view.open(), 0)

    # --------- BACK BUTTON HANDLING ---------
    def on_keyboard(self, window, key, scancode, codepoint, modifiers):
        if key == 27:
            return self.handle_back_button()
        return False

    def handle_back_button(self):
        now = time.time()
        if now - self.last_back_press_time < 1.5:
            self.exit_app()
        else:
            self.last_back_press_time = now
            self.status_label.text = "Press back again to exit."
        return True

    def exit_app(self):
        logging.info("Exit requested.")
        App.get_running_app().stop()

    # --------- PIN LOGIN ---------
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
        unlock_btn.bind(on_press=self.on_unlock_pressed)

        self.login_status_label = Label(text="", size_hint=(1, None), height=30)

        layout.add_widget(title)
        layout.add_widget(subtitle)
        layout.add_widget(self.pin_input)
        layout.add_widget(unlock_btn)
        layout.add_widget(self.login_status_label)

        self.login_view.add_widget(layout)

    def on_unlock_pressed(self, instance):
        try:
            pin = self.pin_input.text.strip()

            if len(pin) != 4 or not pin.isdigit():
                self.login_status_label.text = "PIN must be 4 digits."
                return

            if self.stored_pin is None:
                self.stored_pin = pin
                self.save_pin(pin)
                self.login_status_label.text = "PIN set."
                self.pin_input.text = ""
                Clock.schedule_once(lambda dt: self.login_view.dismiss(), 0.5)
                logging.info("PIN set for first time.")
            else:
                if pin == self.stored_pin:
                    self.login_status_label.text = "Welcome."
                    self.pin_input.text = ""
                    Clock.schedule_once(lambda dt: self.login_view.dismiss(), 0.2)
                    logging.info("PIN accepted.")
                else:
                    self.login_status_label.text = "Incorrect PIN."
                    logging.warning("Wrong PIN entered.")
        except Exception:
            log_exception("on_unlock_pressed failed")

    def load_pin(self):
        try:
            with open(self.pin_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.stored_pin = data.get("pin")
        except FileNotFoundError:
            self.stored_pin = None
        except Exception:
            log_exception("load_pin failed")
            self.stored_pin = None

    def save_pin(self, pin: str):
        try:
            with open(self.pin_file, "w", encoding="utf-8") as f:
                json.dump({"pin": pin}, f, ensure_ascii=False, indent=2)
        except Exception:
            log_exception("save_pin failed")

    # --------- STATS ---------
    def load_stats(self):
        try:
            with open(self.stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.total_sent = int(data.get("total_sent", 0))
        except FileNotFoundError:
            self.total_sent = 0
        except Exception:
            log_exception("load_stats failed")
            self.total_sent = 0

    def save_stats(self):
        try:
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump({"total_sent": self.total_sent}, f, ensure_ascii=False, indent=2)
        except Exception:
            log_exception("save_stats failed")

    def update_total_label(self):
        def _update(dt):
            if self.total_label:
                self.total_label.text = f"Total emails sent: {self.total_sent}"
        Clock.schedule_once(_update, 0)

    # --------- LOADING OVERLAY ---------
    def create_loading_view(self):
        self.loading_view = ModalView(size_hint=(0.6, 0.25), auto_dismiss=False)
        inner = BoxLayout(orientation="vertical", padding=20, spacing=10)

        label_title = Label(text="Sending...", font_size="18sp", size_hint=(1, None), height=30)
        self.loading_label = Label(text="Please wait", size_hint=(1, None), height=30)

        inner.add_widget(label_title)
        inner.add_widget(self.loading_label)

        self.loading_view.add_widget(inner)

    def show_loading(self, message="Sending..."):
        def _show(dt):
            self.loading_label.text = message
            if not self.loading_view.parent:
                self.loading_view.open()
        Clock.schedule_once(_show, 0)

    def hide_loading_and_set_status(self, status_text="Done!"):
        def _hide(dt):
            if self.loading_view.parent:
                self.loading_view.dismiss()
            self.status_label.text = status_text
            self.send_button.disabled = False
        Clock.schedule_once(_hide, 0)

    # --------- MENU ---------
    def create_menu_view(self):
        self.menu_view = ModalView(size_hint=(0.6, 0.5), auto_dismiss=True)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        title = Label(text="Menu", font_size="18sp", size_hint=(1, None), height=30)

        reset_btn = Button(
            text="Reset mails",
            size_hint=(1, None),
            height=45,
            background_normal="",
            background_color=(0.8, 0.4, 0.2, 1),
        )
        reset_btn.bind(on_press=self.on_reset_mails_pressed)

        exit_btn = Button(
            text="Exit",
            size_hint=(1, None),
            height=45,
            background_normal="",
            background_color=(0.7, 0.2, 0.2, 1),
        )
        exit_btn.bind(on_press=self.on_exit_pressed)

        close_btn = Button(
            text="Close",
            size_hint=(1, None),
            height=40,
            background_normal="",
            background_color=(0.7, 0.7, 0.7, 1),
        )
        close_btn.bind(on_press=lambda instance: self.menu_view.dismiss())

        layout.add_widget(title)
        layout.add_widget(reset_btn)
        layout.add_widget(exit_btn)
        layout.add_widget(close_btn)

        self.menu_view.add_widget(layout)

    def on_menu_pressed(self, instance):
        if self.menu_view:
            self.menu_view.open()

    def on_reset_mails_pressed(self, instance):
        try:
            if self.sent_file and os.path.exists(self.sent_file):
                os.remove(self.sent_file)
            self.total_sent = 0
            self.save_stats()
            self.update_total_label()
            self.status_label.text = "Mail history reset. Total emails sent: 0."
            logging.info("Mail history reset.")
        except Exception:
            log_exception("on_reset_mails_pressed failed")
            self.status_label.text = "Error resetting mails."
        finally:
            self.menu_view.dismiss()

    def on_exit_pressed(self, instance):
        self.menu_view.dismiss()
        self.exit_app()

    # --------- SENDER MODAL ---------
    def create_sender_modal(self):
        self.sender_modal = ModalView(size_hint=(0.9, 0.5), auto_dismiss=True)
        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        self.sender_modal_title = Label(text="Add sender email", font_size="18sp", size_hint=(1, None), height=30)

        self.sender_email_input = TextInput(
            hint_text="Sender email (Gmail)",
            multiline=False,
            size_hint=(1, None),
            height=40,
        )

        self.sender_password_input = TextInput(
            hint_text="App Password (16 chars)",
            multiline=False,
            password=True,
            size_hint=(1, None),
            height=40,
        )

        btn_row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=45, spacing=10)

        save_btn = Button(text="Save", size_hint=(0.5, 1), background_normal="", background_color=(0.1, 0.6, 0.5, 1))
        save_btn.bind(on_press=self.on_sender_save)

        cancel_btn = Button(text="Cancel", size_hint=(0.5, 1), background_normal="", background_color=(0.6, 0.6, 0.6, 1))
        cancel_btn.bind(on_press=lambda instance: self.sender_modal.dismiss())

        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)

        layout.add_widget(self.sender_modal_title)
        layout.add_widget(self.sender_email_input)
        layout.add_widget(self.sender_password_input)
        layout.add_widget(btn_row)

        self.sender_modal.add_widget(layout)

    def on_add_sender_pressed(self, instance):
        self.editing_sender_index = None
        self.sender_modal_title.text = "Add sender email"
        self.sender_email_input.text = ""
        self.sender_password_input.text = ""
        self.sender_modal.open()

    def on_sender_edit(self, index):
        if index < 0 or index >= len(self.senders):
            return
        self.editing_sender_index = index
        sender = self.senders[index]
        self.sender_modal_title.text = "Edit sender email"
        self.sender_email_input.text = sender["email"]
        self.sender_password_input.text = sender["password"]
        self.sender_modal.open()

    def on_sender_delete(self, index):
        if index < 0 or index >= len(self.senders):
            return
        del self.senders[index]
        self.update_senders_ui()
        self.status_label.text = "Sender deleted."
        self.save_config()
        logging.info("Sender deleted index=%s", index)

    def on_sender_save(self, instance):
        email = self.sender_email_input.text.strip()
        password = self.sender_password_input.text.strip()

        if not email or not password:
            self.status_label.text = "Sender email and App Password are required."
            return

        if self.editing_sender_index is None:
            self.senders.append({"email": email, "password": password})
            self.status_label.text = "Sender added."
            logging.info("Sender added: %s", email)
        else:
            self.senders[self.editing_sender_index] = {"email": email, "password": password}
            self.status_label.text = "Sender updated."
            logging.info("Sender updated: %s", email)

        self.sender_modal.dismiss()
        self.update_senders_ui()
        self.save_config()

    def update_senders_ui(self):
        for child in list(self.senders_layout.children):
            self.senders_layout.remove_widget(child)

        for idx, sender in enumerate(self.senders):
            row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40, spacing=5)

            email_label = Label(text=sender["email"], size_hint=(0.6, 1))

            edit_btn = Button(text="Edit", size_hint=(0.2, 1), background_normal="", background_color=(0.1, 0.6, 0.5, 1))
            delete_btn = Button(text="Delete", size_hint=(0.2, 1), background_normal="", background_color=(0.8, 0.3, 0.3, 1))

            edit_btn.bind(on_press=lambda inst, i=idx: self.on_sender_edit(i))
            delete_btn.bind(on_press=lambda inst, i=idx: self.on_sender_delete(i))

            row.add_widget(email_label)
            row.add_widget(edit_btn)
            row.add_widget(delete_btn)

            self.senders_layout.add_widget(row)

    # --------- RECIPIENTS ---------
    def on_add_recipient(self, instance=None, initial_value=""):
        row = BoxLayout(orientation="horizontal", size_hint=(1, None), height=40, spacing=5)

        inp = TextInput(text=initial_value, hint_text="Recipient email", multiline=False)

        btn = Button(text="X", size_hint=(None, 1), width=50, background_normal="", background_color=(0.8, 0.3, 0.3, 1))

        def remove_row(btn_instance):
            if row in self.recipients_layout.children:
                self.recipients_layout.remove_widget(row)
            if inp in self.recipient_inputs:
                self.recipient_inputs.remove(inp)

        btn.bind(on_press=remove_row)

        row.add_widget(inp)
        row.add_widget(btn)

        self.recipients_layout.add_widget(row)
        self.recipient_inputs.append(inp)

    def get_recipients_from_ui(self):
        return [inp.text.strip() for inp in self.recipient_inputs if inp.text.strip()]

    # --------- CONFIG ---------
    def get_config_from_ui(self):
        max_emails_text = self.max_emails_input.text.strip()
        if max_emails_text == "":
            max_emails = 2
        else:
            try:
                max_emails = int(max_emails_text)
                if max_emails <= 0:
                    max_emails = 1
            except ValueError:
                max_emails = 2

        recipients = self.get_recipients_from_ui()

        return {"senders": self.senders, "recipients": recipients, "max_emails": max_emails}

    def apply_config_to_ui(self, config):
        self.senders = config.get("senders", [])
        self.update_senders_ui()

        max_emails = config.get("max_emails", 2)
        self.max_emails_input.text = str(max_emails)

        for child in list(self.recipients_layout.children):
            self.recipients_layout.remove_widget(child)
        self.recipient_inputs.clear()

        recipients = config.get("recipients", [])
        if not recipients:
            self.on_add_recipient()
        else:
            for r in recipients:
                self.on_add_recipient(initial_value=r)

    def save_config(self):
        cfg = self.get_config_from_ui()

        if not cfg["senders"]:
            self.status_label.text = "At least one sender is required."
            return
        if not cfg["recipients"]:
            self.status_label.text = "At least one recipient is required."
            return

        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.status_label.text = "Settings saved."
            logging.info("Settings saved.")
        except Exception:
            log_exception("save_config failed")
            self.status_label.text = "Error saving settings."

    def load_config(self):
        if not self.config_file or not os.path.exists(self.config_file):
            self.on_add_recipient()
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.apply_config_to_ui(cfg)
            self.status_label.text = "Settings loaded."
            logging.info("Settings loaded.")
        except Exception:
            log_exception("load_config failed")
            self.status_label.text = "Error loading settings."
            self.on_add_recipient()

    # --------- SEND FLOW ---------
    def on_save_pressed(self, instance):
        self.save_config()

    def on_send_pressed(self, instance):
        if not self.senders:
            self.status_label.text = "At least one sender is required."
            return

        recipients = self.get_recipients_from_ui()
        if not recipients:
            self.status_label.text = "At least one recipient is required."
            return

        max_emails_text = self.max_emails_input.text.strip()
        if max_emails_text == "":
            max_emails = 2
        else:
            try:
                max_emails = int(max_emails_text)
                if max_emails <= 0:
                    max_emails = 1
            except ValueError:
                max_emails = 2

        self.save_config()

        self.send_button.disabled = True
        self.status_label.text = "Starting to send..."
        self.show_loading("Sending...")

        t = threading.Thread(target=self.send_news_flow, daemon=True)
        t.start()

    def send_news_flow(self):
        try:
            cfg = self.get_config_from_ui()
            senders = cfg["senders"]
            recipients = cfg["recipients"]
            max_emails = cfg["max_emails"]

            sent_titles = load_sent_titles(self.sent_file)
            self._log_thread_safe(f"Previously sent: {len(sent_titles)}")

            all_items = collect_news()
            self._log_thread_safe(f"Total collected: {len(all_items)}")

            new_items = [(t, s) for (t, s) in all_items if t not in sent_titles]
            self._log_thread_safe(f"New items: {len(new_items)}")

            if not new_items:
                self.hide_loading_and_set_status("No new items to send.")
                return

            to_send = new_items[:max_emails]
            self._log_thread_safe(f"Sending {len(to_send)} items from {len(senders)} senders...")

            emails_this_round = len(senders) * len(to_send)

            for sender in senders:
                sender_email = sender["email"]
                app_password = sender["password"]
                self._log_thread_safe(f"Sending from {sender_email}...")
                send_emails(
                    sender_email,
                    app_password,
                    recipients,
                    to_send,
                    log_func=self._log_thread_safe,
                )

            titles_just_sent = [t for (t, _) in to_send]
            append_sent_titles(self.sent_file, titles_just_sent)

            self.total_sent += emails_this_round
            self.save_stats()
            self.update_total_label()

            self.hide_loading_and_set_status(f"Done! Total emails sent: {self.total_sent}")
            logging.info("Send flow finished OK.")

        except Exception:
            log_exception("send_news_flow crashed")
            self.hide_loading_and_set_status("Error. Check app.log.")

    def _log_thread_safe(self, text: str):
        def _update(dt):
            self.status_label.text = text
        Clock.schedule_once(_update, 0)


if __name__ == "__main__":
    NewsApp().run()
