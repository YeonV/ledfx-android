# LedFx Root Audio Capture - runs on every boot (late_start service)
#
# Two independent, idempotent jobs - safe to run every single boot forever,
# both no-op quickly once there is nothing left to do.
#
# Job 1: _ssl.cpython-*.so / _hashlib.cpython-*.so live in the app's PRIVATE
# storage, extracted fresh from libpybundle.so on first launch after every
# version bump. customize.sh can never reach them - they do not exist until
# LedFx has actually launched at least once. Patch them here instead, once
# they show up.
#
# Job 2: a normal LedFx update (sideloaded from GitHub releases, not
# through this module) creates a /data/app update layer that SHADOWS the
# systemized /system/priv-app copy. Per Android's own security design, that
# shadow layer never gets the privileged permission grant - only the
# underlying /system-resident APK does (confirmed by hand: a plain
# `pm install -r` update layer showed the permission requested but NOT
# granted; only after `pm uninstall` reverted it back onto the system
# baseline did `dumpsys package` show granted=true). Detect the shadow and
# re-systemize automatically, so an ordinary LedFx update self-heals on the
# next boot instead of silently losing root audio capture until someone
# remembers to re-flash this module by hand.

MODDIR="${0%/*}"
. "$MODDIR/common.sh"

PKG="com.ledfx.ledfx"

# late_start service already implies data is decrypted and available: this
# is just headroom for LedFx's own boot-time work, not a correctness
# requirement.
sleep 15

# --- Job 1: patch the private-storage ssl modules, if present ---
DATADIR="/data/user/0/$PKG/files/app/_python_bundle/modules"
SSL_SO=$(ls "$DATADIR"/_ssl.cpython-*.so 2>/dev/null | head -1)
HASHLIB_SO=$(ls "$DATADIR"/_hashlib.cpython-*.so 2>/dev/null | head -1)

if [ -n "$SSL_SO" ]; then
  OWNER=$(stat -c '%u:%g' "$SSL_SO" 2>/dev/null)
  patch_elf_string "$SSL_SO" "libssl.so"    "libssx.so"
  patch_elf_string "$SSL_SO" "libcrypto.so" "libcryptx.so"
  [ -n "$OWNER" ] && chown "$OWNER" "$SSL_SO"
fi
if [ -n "$HASHLIB_SO" ]; then
  OWNER=$(stat -c '%u:%g' "$HASHLIB_SO" 2>/dev/null)
  patch_elf_string "$HASHLIB_SO" "libcrypto.so" "libcryptx.so"
  [ -n "$OWNER" ] && chown "$OWNER" "$HASHLIB_SO"
fi

# --- Job 2: self-heal a shadowing update ---
ACTIVE_PATH=$(pm path "$PKG" 2>/dev/null | sed 's/^package://')
case "$ACTIVE_PATH" in
  /system/priv-app/LedFx/*|"")
    # Already the systemized copy, or the package didn't resolve (e.g. not
    # installed at all) - nothing to heal either way.
    ;;
  *)
    log -t LedFxRootAudio "Detected shadowing update at $ACTIVE_PATH, re-systemizing"

    DEST="/system/priv-app/LedFx"
    mkdir -p "$DEST/lib/arm"
    cp -f "$ACTIVE_PATH" "$DEST/LedFx.apk"

    UNPACK="/data/local/tmp/.ledfx_rootaudio_unpack"
    rm -rf "$UNPACK"; mkdir -p "$UNPACK"
    unzip -oq "$DEST/LedFx.apk" "lib/armeabi-v7a/*" -d "$UNPACK"
    cp -f "$UNPACK"/lib/armeabi-v7a/*.so "$DEST/lib/arm/"
    rm -rf "$UNPACK"

    patch_ssl_libs "$DEST/lib/arm"

    chown -R 0:0 "$DEST"
    find "$DEST" -type d -exec chmod 0755 {} \;
    find "$DEST" -type f -exec chmod 0644 {} \;

    # Force PackageManager to notice the changed priv-app content (it caches
    # by default and won't re-scan on its own), then immediately revert the
    # resulting update layer back onto the system baseline - that revert is
    # what actually grants the privileged permission, not the install.
    pm install -r "$DEST/LedFx.apk" >/dev/null 2>&1
    pm uninstall "$PKG" >/dev/null 2>&1

    # The new version's _ssl.so/_hashlib.so will not exist until LedFx is
    # launched at least once, and will not be patched until the boot after
    # that - Job 1 above picks them up automatically once they appear, same
    # as it does after a fresh module install. No further action needed
    # here.
    log -t LedFxRootAudio "Re-systemize complete"
    ;;
esac
