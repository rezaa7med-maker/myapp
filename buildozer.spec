[app]
title = My Application
package.name = myapp
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 0.1
requirements = python3,kivy==2.3.0,requests,feedparser==6.0.11,certifi,pyjnius,arabic-reshaper,python-bidi

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.sdk_build_tools = 34.0.0
android.enable_immersive_mode = False
