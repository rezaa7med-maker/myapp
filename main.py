import os
import certifi
import feedparser
from kivy.app import App
from kivy.uix.label import Label

RSS_URL = "https://www.tabnak.ir/fa/rss/allnews"

class MyApp(App):
    def build(self):
        try:
            os.environ["SSL_CERT_FILE"] = certifi.where()
            feed = feedparser.parse(RSS_URL)
            title = feed.entries[0].title if feed.entries else "No entries"
            return Label(text=title)
        except Exception as e:
            return Label(text=str(e))

if __name__ == "__main__":
    MyApp().run()
