[app]
title = Campaign
package.name = myapp
package.domain = com.rezaa7med.campaign

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.2
android.numeric_version = 2
requirements = python3,kivy==2.3.0,requests,feedparser==6.0.11,certifi,pyjnius

orientation = portrait
fullscreen = 0

# --- FIXED: add needed locks + wifi permissions
android.permissions = INTERNET, ACCESS_NETWORK_STATE, WAKE_LOCK, ACCESS_WIFI_STATE, CHANGE_WIFI_STATE

android.api = 31
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.sdk_build_tools = 31.0.0
android.enable_immersive_mode = False
