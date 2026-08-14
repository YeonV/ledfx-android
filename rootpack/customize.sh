# LedFx Root Audio Capture - install-time setup
#
# The system-resident copy is a bundled, code-free stub (stub.apk) - not a
# copy of the real LedFx install. It only needs to exist as a signed,
# privileged-permission-declaring anchor for PackageManager to recognize at
# boot; it is never actually executed (confirmed by hand: pm path always
# resolves to the real, functional /data/app install regardless, and the
# privileged permission grant cascades down to it anyway). That means the
# stub never goes stale across LedFx releases and never needs touching
# again - unlike an earlier version of this module that copied the real
# APK's native libs/Python bundle into place, which required renaming its
# bundled OpenSSL to dodge a collision with the system's own BoringSSL, and
# that rename had its own ordering bugs when it ran out of sync with the
# real app's actual install state. None of that applies to a stub with no
# code at all.
#
# service.sh repeats the stub placement on every boot in case the module's
# own OverlayFS mount never actually applies (device-dependent) - keep the
# two in sync if you change this file.

. "$MODPATH/common.sh"

PKG="com.ledfx.ledfx"
REQUIRED_PERMS="CAPTURE_AUDIO_OUTPUT QUERY_AUDIO_STATE"

ui_print "- Looking for an installed LedFx..."
APK_PATH=$(pm path "$PKG" 2>/dev/null | sed 's/^package://')
if [ -z "$APK_PATH" ] || [ ! -f "$APK_PATH" ]; then
  ui_print "! LedFx is not installed."
  ui_print "! Install it from the GitHub releases page first, then re-run this module."
  abort "LedFx not found"
fi
ui_print "- Found: $APK_PATH"

ui_print "- Checking the installed build requests the permissions this needs..."
DUMP=$(dumpsys package "$PKG" 2>/dev/null)
for perm in $REQUIRED_PERMS; do
  if ! echo "$DUMP" | grep -q "android.permission.$perm"; then
    ui_print "! Installed LedFx does not request android.permission.$perm."
    ui_print "! Update to a newer LedFx release, then re-run this module."
    abort "missing required permission: $perm"
  fi
done
ui_print "- OK."

DEST="$MODPATH/system/priv-app/LedFx"
mkdir -p "$DEST"
mkdir -p "$MODPATH/system/etc/permissions"

ui_print "- Placing the permission-anchor stub..."
cp -f "$MODPATH/stub.apk" "$DEST/LedFx.apk"

ui_print "- Writing the privileged-permission whitelist..."
cat > "$MODPATH/system/etc/permissions/privapp-permissions-ledfx.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<permissions>
    <privapp-permissions package="$PKG">
        <permission name="android.permission.CAPTURE_AUDIO_OUTPUT" />
        <permission name="android.permission.QUERY_AUDIO_STATE" />
    </privapp-permissions>
</permissions>
EOF

set_perm_recursive "$MODPATH/system" 0 0 0755 0644

ui_print "- Done. Reboot to activate."
ui_print "- After rebooting, open LedFx once and give it a moment on first"
ui_print "  launch - 'System Audio (root)' will then appear in Settings -> Audio."
