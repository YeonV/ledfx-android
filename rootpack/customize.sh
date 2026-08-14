# LedFx Root Audio Capture - install-time setup
#
# Deliberately does NOT bundle a copy of the LedFx APK. It systemizes
# whatever LedFx build the user already has installed from the normal
# release channel (GitHub releases), because bundling our own copy would go
# stale every LedFx release - we hit exactly that problem by hand during
# development (the bundled OpenSSL's exact bytes differed between two
# consecutive LedFx builds even at the same file size, so a pre-patched
# copy from one build silently didn't match the next). Re-deriving from
# whatever's actually installed means this can never go stale.
#
# service.sh repeats this same logic on every boot to self-heal after a
# normal LedFx update - keep the two in sync if you change this file.

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
mkdir -p "$DEST/lib/arm"
mkdir -p "$MODPATH/system/etc/permissions"

ui_print "- Copying the APK..."
cp -f "$APK_PATH" "$DEST/LedFx.apk"

ui_print "- Extracting native libraries..."
# A raw priv-app placement (as opposed to a normal pm install) does not
# auto-extract native libs the way the package installer does - has to be
# done by hand, once here and again in service.sh's self-heal path.
UNPACK="$MODPATH/_unpack_tmp"
rm -rf "$UNPACK"; mkdir -p "$UNPACK"
unzip -oq "$DEST/LedFx.apk" "lib/armeabi-v7a/*" -d "$UNPACK"
cp -f "$UNPACK"/lib/armeabi-v7a/*.so "$DEST/lib/arm/"
rm -rf "$UNPACK"

ui_print "- Patching the OpenSSL naming collision..."
patch_ssl_libs "$DEST/lib/arm"

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
