# LedFx Root Audio Capture - post-fs-data, before PackageManager's boot scan
#
# Mounts this module's own system/ files, so systemization works without a
# KernelSU metamodule. KernelSU-Next 3.x no longer mounts module system/
# directories itself - that is delegated to a metamodule, and with none
# installed nothing gets mounted (KernelSU-Next docs, guide/metamodule.md).
# service.sh's direct-write fallback cannot help on a device whose / stays
# read-only after `mount -o remount,rw /` (confirmed on a Pixel 8).
#
# Read-only overlays stacked on /system/priv-app and /system/etc/permissions,
# with this module's files as the upper lower-layer. overlayfs rejects the
# module directory itself as a layer on that Pixel 8 (dmesg: "overlayfs:
# filesystem on '/data/adb/modules/...' not supported"), so the files are
# copied into a tmpfs first and the overlay is built from there. Verified by
# hand in a private mount namespace before going anywhere near a boot.
#
# Nothing persists: the tmpfs and both overlays are gone on the next boot, so
# disabling or removing the module reverts this with a plain reboot.

MODDIR="${0%/*}"
PRIV="$MODDIR/system/priv-app/LedFx/LedFx.apk"
PERM="$MODDIR/system/etc/permissions/privapp-permissions-ledfx.xml"
T=/dev/ledfx_ov

# Already systemized (by a metamodule, a writable /, or an earlier run).
if [ -f /system/priv-app/LedFx/LedFx.apk ] && [ -f /system/etc/permissions/privapp-permissions-ledfx.xml ]; then
  exit 0
fi

if [ ! -f "$PRIV" ] || [ ! -f "$PERM" ]; then
  log -t LedFxRootAudio "post-fs-data: module system/ files missing, nothing to mount"
  exit 0
fi

mkdir -p "$T"
if ! mount -t tmpfs -o mode=755 tmpfs "$T"; then
  log -t LedFxRootAudio "post-fs-data: tmpfs mount on $T failed"
  rmdir "$T" 2>/dev/null
  exit 0
fi

mkdir -p "$T/priv-app/LedFx" "$T/permissions"
cp -f "$PRIV" "$T/priv-app/LedFx/LedFx.apk"
cp -f "$PERM" "$T/permissions/privapp-permissions-ledfx.xml"
chown -R 0:0 "$T/priv-app" "$T/permissions"
chmod 0755 "$T/priv-app/LedFx"
chmod 0644 "$T/priv-app/LedFx/LedFx.apk" "$T/permissions/privapp-permissions-ledfx.xml"
chcon -R u:object_r:system_file:s0 "$T/priv-app" "$T/permissions"

# Whitelist first, stub only once it is in place: a privileged app without
# its privapp-permissions entry is exactly what enforce mode refuses.
if ! mount -t overlay overlay -o "ro,lowerdir=$T/permissions:/system/etc/permissions" /system/etc/permissions; then
  log -t LedFxRootAudio "post-fs-data: permissions overlay failed, stub not mounted, see dmesg 'overlayfs:'"
  exit 0
fi
if mount -t overlay overlay -o "ro,lowerdir=$T/priv-app:/system/priv-app" /system/priv-app; then
  log -t LedFxRootAudio "post-fs-data: privapp XML and stub overlaid onto /system"
else
  log -t LedFxRootAudio "post-fs-data: priv-app overlay failed, see dmesg 'overlayfs:'"
fi
