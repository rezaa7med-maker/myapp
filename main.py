import feedparser
from kivy.app import App
from kivy.uix.label import Label

RSS_URL = "https://feeds.bbci.co.uk/persian/rss.xml"

class MyApp(App):
    def build(self):
        try:
            feed = feedparser.parse(RSS_URL)
            if feed.entries:
                title = feed.entries[0].title
            else:
                title = "No entries"
            return Label(text=title)
        except Exception as e:
            return Label(text=str(e))

if __name__ == "__main__":
    MyApp().run()
