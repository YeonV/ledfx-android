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
# Job 2: places the bundled permission-anchor stub (stub.apk - see
# customize.sh) directly at /system/priv-app/LedFx in case the module's own
# OverlayFS mount never actually applies. That's device-dependent: on at
# least one test device, the mount never mounts at all (no metamodule
# providing it), so this direct write is what actually makes systemization
# happen there. Cheap and unconditional since the stub is tiny and static -
# unlike an earlier version of this job, which copied the real, currently-
# installed LedFx APK and its native libs into place and had to detect
# "shadowing" updates to stay in sync. A stub never goes stale, so there is
# nothing to detect or resync here anymore.

MODDIR="${0%/*}"
. "$MODDIR/common.sh"

PKG="com.ledfx.ledfx"

# late_start service already implies data is decrypted and available: this
# is just headroom for LedFx's own boot-time work, not a correctness
# requirement.
sleep 15

# Which install pm actually resolves to right now - Job 1 keys off this.
ACTIVE_PATH=$(pm path "$PKG" 2>/dev/null | sed 's/^package://')

# --- Job 1: patch the private-storage ssl modules, if present ---
#
# Only when the systemized copy is the one pm actually resolves to. The
# renamed libssx.so/libcryptx.so only exist under that copy's own
# lib/arm/, and the private module's dlopen only ever searches its own
# app's native-lib directory - a privileged SELinux context does NOT
# expand the linker namespace to reach /system/lib or another app's
# directory (confirmed by hand: publishing the renamed libs to
# /system/lib made no difference, the crash was identical). So if pm
# still resolves to the /data/app update layer - which happens on at
# least one test device even *after* the privileged permission is
# granted via the system baseline underneath it - renaming here would
# leave the private module needing a library its own namespace can never
# find. Skip it in that case and let the module keep using stock
# libssl.so/libcrypto.so, which works fine as long as this app's own
# namespace never actually escalates to one that can see a conflicting
# system-side OpenSSL - reproduced and confirmed working by hand.
DATADIR="/data/user/0/$PKG/files/app/_python_bundle/modules"
SSL_SO=$(ls "$DATADIR"/_ssl.cpython-*.so 2>/dev/null | head -1)
HASHLIB_SO=$(ls "$DATADIR"/_hashlib.cpython-*.so 2>/dev/null | head -1)

case "$ACTIVE_PATH" in
  /system/priv-app/LedFx/*)
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
    ;;
esac

# --- Job 2: make sure the permission-anchor stub is in place ---
DEST="/system/priv-app/LedFx"
STUB="$MODDIR/stub.apk"

if [ ! -f "$STUB" ]; then
  log -t LedFxRootAudio "stub.apk missing from module dir, nothing to do"
elif ! cmp -s "$STUB" "$DEST/LedFx.apk" 2>/dev/null; then
  mount -o remount,rw / 2>/dev/null

  mkdir -p "$DEST"
  cp -f "$STUB" "$DEST/LedFx.apk"

  if [ ! -s "$DEST/LedFx.apk" ]; then
    log -t LedFxRootAudio "Could not write $DEST/LedFx.apk (still read-only?)"
  else
    chown 0:0 "$DEST/LedFx.apk"
    chmod 0644 "$DEST/LedFx.apk"

    mkdir -p /system/etc/permissions
    cat > /system/etc/permissions/privapp-permissions-ledfx.xml <<EOF
<?xml version="1.0" encoding="utf-8"?>
<permissions>
    <privapp-permissions package="$PKG">
        <permission name="android.permission.CAPTURE_AUDIO_OUTPUT" />
        <permission name="android.permission.QUERY_AUDIO_STATE" />
    </privapp-permissions>
</permissions>
EOF
    chown 0:0 /system/etc/permissions/privapp-permissions-ledfx.xml
    chmod 0644 /system/etc/permissions/privapp-permissions-ledfx.xml

    log -t LedFxRootAudio "Stub placed at $DEST - takes effect after the next reboot"
  fi
fi
