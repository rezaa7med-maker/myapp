[app]
title = Campaign2
package.name = myapp2
package.domain = com.rezaa7med.campaign2
icon.filename = icon.png

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.2
android.numeric_version = 2
requirements = hostpython3==3.12.7, python3==3.12.7, kivy==2.3.0, requests, feedparser==6.0.11, certifi, pyjnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE

android.api = 31
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.sdk_build_tools = 31.0.0
android.enable_immersive_mode = False
