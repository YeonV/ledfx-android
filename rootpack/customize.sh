# LedFx Root Audio Capture - install-time setup
#
# Flashing this zip sets up everything a rooted user needs:
#   1. LedFx itself, downloaded from the module's own release when it is
#      missing or older than that release.
#   2. The Now Playing addon, same rule, with its notification listener
#      switched on.
#   3. The privileged permissions (stub + whitelist below) and the RECORD_AUDIO
#      runtime grant, so nothing is asked on first launch.
# Step 2 is one volume-key question; with no key pressed it is installed.
#
# Downloads come from the module's OWN release (release.env, written by CI),
# never /releases/latest: that endpoint skips pre-releases and would hand a
# pre-release module an older LedFx that lacks the permissions this needs.
# busybox wget does not validate TLS certificates, so every download is checked
# against the SHA-256 CI recorded in release.env and refused on a mismatch.
# A module built without release.env (a local build) behaves as before: LedFx
# must already be installed.
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
# The system/ files staged here only reach /system if something mounts them.
# KernelSU-Next 3.x leaves that to a metamodule, so post-fs-data.sh mounts
# them itself on every boot when nothing else has; service.sh's direct write
# is the last fallback, for a device where / can be remounted rw. Keep all
# three in sync if you change the files placed here.

. "$MODPATH/common.sh"

PKG="com.ledfx.ledfx"
ADDON_PKG="com.ledfx.nowplaying"
ADDON_LISTENER="$ADDON_PKG/$ADDON_PKG.NowPlayingListenerService"
REQUIRED_PERMS="CAPTURE_AUDIO_OUTPUT QUERY_AUDIO_STATE"
TMP=/data/local/tmp/ledfx_module

HAVE_RELEASE=0
if [ -f "$MODPATH/release.env" ]; then
  . "$MODPATH/release.env"
  HAVE_RELEASE=1
fi

# --- volume-key question -----------------------------------------------------

OPT_ADDON=1

# wait_key <seconds> - prints up, down or none. Reacts to key-down events only:
# getevent also reports the release and the repeats of a held key.
wait_key() {
  end=$(( $(date +%s) + $1 ))
  while :; do
    left=$(( end - $(date +%s) ))
    [ "$left" -le 0 ] && { echo none; return; }
    ev=$(timeout "$left" getevent -lqc 1 2>/dev/null)
    case "$ev" in
      *KEY_VOLUMEUP*DOWN*) echo up; return ;;
      *KEY_VOLUMEDOWN*DOWN*) echo down; return ;;
    esac
  done
}

ask_addon() {
  ui_print " "
  ui_print "- Install the Now Playing addon? It shows the playing song in"
  ui_print "  LedFx and gets notification access to read media sessions."
  ui_print "  Vol+ = yes, Vol- = no (no key for 10 s = yes)"
  case "$(wait_key 10)" in
    down) OPT_ADDON=0; ui_print "  -> no" ;;
    up) ui_print "  -> yes" ;;
    *) ui_print "  -> yes (no key)" ;;
  esac
  ui_print " "
}

# --- download + install ------------------------------------------------------

BB=""
for b in /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /data/adb/magisk/busybox; do
  [ -x "$b" ] && { BB="$b"; break; }
done

# installed_vc <package> - the active versionCode, empty if not installed.
installed_vc() {
  pm list packages --show-versioncode "$1" 2>/dev/null \
    | grep "^package:$1 " | sed 's/.*versionCode://' | head -1
}

# fetch <asset name> <sha256> <out file> - download from this module's release
# and check the hash. Returns non-zero, with the reason printed, on any failure.
fetch() {
  name="$1"; sha="$2"; out="$3"
  if [ -z "$BB" ]; then
    ui_print "! No busybox found for downloading."
    return 1
  fi
  url="https://github.com/$RELEASE_REPO/releases/download/$RELEASE_TAG/$name"
  ui_print "- Downloading $name ..."
  rm -f "$out"
  if ! "$BB" wget -q -T 10 -O "$out" "$url" 2>/dev/null; then
    ui_print "! Download failed (no internet, or GitHub unreachable)."
    rm -f "$out"
    return 1
  fi
  got=$("$BB" sha256sum "$out" | cut -d' ' -f1)
  if [ "$got" != "$sha" ]; then
    ui_print "! Checksum mismatch, refusing to install it."
    ui_print "!   expected $sha"
    ui_print "!   got      $got"
    rm -f "$out"
    return 1
  fi
  ui_print "- Checksum OK."
}

# ensure_app <label> <package> <asset> <sha256> <versionCode>
# Installs when missing, updates when older, keeps a same or newer install.
ensure_app() {
  label="$1"; pkg="$2"; name="$3"; sha="$4"; want="$5"
  have=$(installed_vc "$pkg")
  if [ -z "$name" ] || [ -z "$sha" ] || [ -z "$want" ]; then
    ui_print "! $label: not part of release $RELEASE_TAG for this device, skipped."
    return 1
  fi
  if [ -n "$have" ] && [ "$have" -ge "$want" ]; then
    ui_print "- $label: installed version is current ($have), no download."
    return 0
  fi
  if [ -n "$have" ]; then
    ui_print "- $label: installed $have is older than $want, updating."
  else
    ui_print "- $label: not installed, installing $RELEASE_TAG."
  fi
  mkdir -p "$TMP"
  apk="$TMP/$pkg.apk"
  fetch "$name" "$sha" "$apk" || return 1
  res=$(pm install -r "$apk" 2>&1)
  rm -f "$apk"
  case "$res" in
    *Success*) ui_print "- $label: installed." ; return 0 ;;
    *UPDATE_INCOMPATIBLE*)
      ui_print "! $label: the installed copy is signed with a different key"
      ui_print "!   (a debug build?). Uninstall it, then flash this module again."
      return 1 ;;
    *)
      ui_print "! $label: install failed: $res"
      return 1 ;;
  esac
}

if [ "$HAVE_RELEASE" = "1" ]; then
  ui_print "- Module for LedFx $RELEASE_TAG"
  ask_addon
  ABI=$(getprop ro.product.cpu.abi | tr '-' '_')
  eval "L_NAME=\$LEDFX_${ABI}_NAME; L_SHA=\$LEDFX_${ABI}_SHA256; L_VC=\$LEDFX_${ABI}_VC"
  ensure_app "LedFx" "$PKG" "$L_NAME" "$L_SHA" "$L_VC"
  if [ "$OPT_ADDON" = "1" ]; then
    if ensure_app "Now Playing addon" "$ADDON_PKG" "$ADDON_NAME" "$ADDON_SHA256" "$ADDON_VC"; then
      if cmd notification allow_listener "$ADDON_LISTENER" >/dev/null 2>&1; then
        ui_print "- Now Playing addon: notification access enabled."
      else
        ui_print "! Now Playing addon: could not enable notification access;"
        ui_print "!   enable it in the addon itself."
      fi
    fi
  else
    ui_print "- Now Playing addon: skipped."
  fi
  rm -rf "$TMP"
fi

# --- privileged permissions ---------------------------------------------------

ui_print "- Looking for an installed LedFx..."
APK_PATH=$(pm path "$PKG" 2>/dev/null | sed 's/^package://' | grep -v '^/system/' | head -1)
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

# Everything LedFx would otherwise ask for on first launch or on its first
# update: flashing a root module already hands it the device, so nothing is
# left for the user to click through.
for perm in RECORD_AUDIO CAMERA; do
  if pm grant "$PKG" "android.permission.$perm" 2>/dev/null; then
    ui_print "- Granted $perm."
  else
    ui_print "! Could not grant $perm; LedFx will ask for it."
  fi
done
# Installing updates is an app-op, not a runtime permission.
if appops set "$PKG" REQUEST_INSTALL_PACKAGES allow 2>/dev/null; then
  ui_print "- Allowed installing updates."
else
  ui_print "! Could not allow installing updates; LedFx will ask when updating."
fi

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
