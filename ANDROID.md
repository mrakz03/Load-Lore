# Android app (kept for a possible relaunch)

This branch keeps Load Lore's Android app as it was when it was dropped (Nov 19 2026, Zeke): from then on
the app is web only (loadlore.net) and `next` / `main` no longer have any Android files.

What made the Android app, all on this branch:
- `package.json`, `capacitor.config.json`: the Capacitor wrapper (appId `com.cartridgecalc.app`; keep it,
  a new appId makes a new app and testers lose their handloads).
- `assets/android/res/`: launcher icons, drawn by `scripts/make_icons.py`.
- `.github/workflows/release.yml`: the `android` job (`npx cap add android`, icons, `gradlew assembleDebug`,
  signing with the `ANDROID_DEBUG_KEYSTORE` secret).
- `web/template.html`: Android-only code: the back button listener (Capacitor App plugin), the Share
  sheet (`@capacitor/share`) in `shareLink`, and the Back up dialog's copy-only mode (`native`).

To bring it back: copy those files / pieces onto the current `next` (or merge this branch's Android
parts), put the `ANDROID_DEBUG_KEYSTORE` secret back if it was deleted (the key is in the project files,
android-key/debug.keystore.base64.txt), and push a tag. The last releases with an APK attached are
v1.14.x and earlier.
