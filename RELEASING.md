# Making a release

Notes for the maintainer.

```
git pull && git tag v1.6 && git push origin v1.6
```
GitHub Actions builds the Windows installer and .zip, the Linux .tar.gz and the Android APK, and publishes them as a release. The tag sets the version the apps show ("Development Build v1.6"; builds from source show "Development Build"). Running the workflow by hand (Actions tab > Run workflow) builds the files without releasing; they appear under the run's Artifacts.

A new APK installs over the old one only if every release is signed with the same key. Make one once (needs Java's `keytool`) and save it as a repository secret named `ANDROID_DEBUG_KEYSTORE` (Settings > Secrets and variables > Actions):
```
keytool -genkeypair -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
base64 -w0 debug.keystore      # paste this output as the secret's value
```
Keep `debug.keystore` somewhere safe and out of the repo. Without the secret, each APK gets a new key and testers have to uninstall the old app before installing a new one.
