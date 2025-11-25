import os
import sys
import traceback

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.window import Window


def write_crash(app_dir, text):
    try:
        os.makedirs(app_dir, exist_ok=True)
        path = os.path.join(app_dir, "crash.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)
        root = BoxLayout(orientation="vertical", padding=20, spacing=10)
        self.label = Label(text="Starting...", font_size="18sp")
        root.add_widget(self.label)
        return root

    def on_start(self):
        Clock.schedule_once(self.safe_boot, 0.2)

    def safe_boot(self, dt):
        try:
            # third-party imports only inside try
            import requests
            import feedparser

            self.label.text = "Imports OK"

            url = "https://www.tabnak.ir/fa/rss/allnews"
            r = requests.get(url, timeout=8)
            feed = feedparser.parse(r.text)
            count = len(getattr(feed, "entries", []) or [])

            self.label.text = f"RSS OK, items: {count}"

        except Exception as e:
            tb = traceback.format_exc()
            self.label.text = "ERROR:\n" + str(e)

            # save crash log
            try:
                app_dir = self.user_data_dir
            except Exception:
                app_dir = "/sdcard"

            write_crash(app_dir, tb)


if __name__ == "__main__":
    try:
        NewsApp().run()
    except Exception:
        tb = traceback.format_exc()
        # last resort save near sdcard
        try:
            os.makedirs("/sdcard", exist_ok=True)
            with open("/sdcard/crash.txt", "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        raise
