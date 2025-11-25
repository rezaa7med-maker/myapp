import os
import certifi
import requests
from kivy.app import App
from kivy.uix.label import Label

URL = "https://www.tabnak.ir/fa/rss/allnews"

class MyApp(App):
    def build(self):
        try:
            os.environ["SSL_CERT_FILE"] = certifi.where()
            r = requests.get(URL, timeout=10)
            txt = r.text[:200]
            return Label(text=txt)
        except Exception as e:
            return Label(text=str(e))

if __name__ == "__main__":
    MyApp().run()
