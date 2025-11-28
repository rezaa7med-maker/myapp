[app]
title = News Mailer
package.name = newsmailer
package.domain = org.rezaabs

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 0.2
requirements = python3,kivy==2.3.0,requests,feedparser==6.0.11,certifi,pyjnius

orientation = portrait

# ✅ جلوگیری از فول‌اسکرین
fullscreen = 0
android.enable_immersive_mode = False

# اگر آیکون/اسپلش داری (اختیاری)
# icon.filename = assets/icon.png
# presplash.filename = assets/presplash.png

android.permissions = INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK

android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a

android.accept_sdk_license = True
android.sdk_build_tools = 34.0.0

# برای حجم کمتر (اختیاری)
android.strip_debug_symbols = True

[buildozer]
log_level = 2
warn_on_root = 1
