from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.core.window import Window

class NewsApp(App):
    def build(self):
        Window.clearcolor = (0, 0, 0, 1)

        root = BoxLayout(orientation="vertical", padding=16, spacing=10)

        root.add_widget(Label(text="Top bar OK"))
        root.add_widget(Button(text="Add sender email"))
        root.add_widget(Button(text="Add recipient"))
        root.add_widget(TextInput(hint_text="Max emails", multiline=False))
        root.add_widget(Button(text="Save"))
        root.add_widget(Button(text="Send"))
        root.add_widget(Label(text="Total emails sent: 0"))
        root.add_widget(Label(text="Status OK"))

        return root

if __name__ == "__main__":
    NewsApp().run()
