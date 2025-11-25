import feedparser
from kivy.app import App
from kivy.uix.label import Label

RSS_URL = "http://feeds.bbci.co.uk/persian/rss.xml"

class MyApp(App):
    def build(self):
        try:
            feed = feedparser.parse(RSS_URL)
            title = feed.entries[0].title if feed.entries else "No entries"
            return Label(text=title)
        except Exception as e:
            return Label(text=str(e))

if __name__ == "__main__":
    MyApp().run()
