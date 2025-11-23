[app]
title = My Application
package.name = myapp
package.domain = org.test
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy,feedparser
orientation = portrait
android.permissions = INTERNET
android.api = 34
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.sdk_build_tools = 34.0.0

[buildozer]
log_level = 2
warn_on_root = 1
