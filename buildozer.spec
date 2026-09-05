[buildozer]
log_level = 2

[app]
title = Campaign3
package.name = myapp3
package.domain = com.rezaa7med.campaign3
icon.filename = icon.png

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.2
android.numeric_version = 2

requirements = hostpython3==3.10.11, python3==3.10.11, kivy==2.3.0, requests, feedparser==6.0.11, certifi

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE

android.api = 31
android.minapi = 21
android.ndk = 25c
android.archs = arm64-v8a
android.accept_sdk_license = True
android.enable_immersive_mode = False

# تنظیمات اضافی برای جلوگیری از مشکل pip
android.p4a_args = --no-upgrade-pip --no-ensurepip --pip-args="--no-cache-dir --disable-pip-version-check --force-reinstall --no-deps"
