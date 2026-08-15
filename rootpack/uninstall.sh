# LedFx Root Audio Capture - runs when KernelSU removes this module
#
# service.sh writes the permission-anchor stub directly to
# /system/priv-app/LedFx and /system/etc/permissions/privapp-permissions-
# ledfx.xml, bypassing the module's own OverlayFS-managed system/ directory
# entirely - a workaround for devices where that mount never actually
# applies (no metamodule providing it; confirmed on a real test device).
# Because that placement lives outside what OverlayFS would normally clean
# up on its own, removing the module alone would never revert it. This is
# what actually reverts it - same remount-rw dance service.sh already does,
# since / is read-only by default at this point regardless of any earlier
# session.

mount -o remount,rw / 2>/dev/null
rm -rf /system/priv-app/LedFx
rm -f /system/etc/permissions/privapp-permissions-ledfx.xml
log -t LedFxRootAudio "Module uninstalled - reverted systemized LedFx, reboot to finish"
