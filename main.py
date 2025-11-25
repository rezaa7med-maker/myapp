import threading
import requests
import feedparser

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.core.window import Window


# --------- CONSTANT DATA ---------
RSS_FEEDS = [
    "https://parsi.euronews.com/index.php/rss?level=program&name=world",
    "https://www.mehrnews.com/index.php?module=persian&func=rss&service_id=1",
    "https://www.tabnak.ir/fa/rss/allnews",
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android) KivyApp/1.0"
}


# --------- RSS SAFE FETCH ---------
def collect_news_safe(log_func=print):
    items = []

    for url in RSS_FEEDS:
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
            r.raise_for_status()

            # Use bytes to avoid encoding issues on Android
            feed = feedparser.parse(r.content)

            if getattr(feed, "bozo", False):
                log_func(f"RSS parse warning for {url}: {getattr(feed, 'bozo_exception', None)}")

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


# --------- MAIN APP ---------
class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)

        root = BoxLayout(orientation="vertical", padding=20, spacing=10)

        self.title_label = Label(
            text="UI OK",
            font_size="22sp",
            size_hint=(1, 0.6),
        )

        self.status_label = Label(
            text="Waiting...",
            font_size="18sp",
            size_hint=(1, 0.4),
        )

        root.add_widget(self.title_label)
        root.add_widget(self.status_label)

        return root

    def on_start(self):
        # after 1 second, test RSS in background thread
        Clock.schedule_once(lambda dt: self.start_rss_thread(), 1)

    def start_rss_thread(self):
        t = threading.Thread(target=self.test_rss_worker, daemon=True)
        t.start()

    def test_rss_worker(self):
        def log(msg):
            Clock.schedule_once(lambda dt: self.set_status(msg), 0)

        news = collect_news_safe(log_func=log)
        log(f"RSS OK, items: {len(news)}")

    def set_status(self, msg):
        self.status_label.text = msg


if __name__ == "__main__":
    NewsApp().run()
