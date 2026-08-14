#!/system/bin/sh
# Shared helpers for the LedFx root-audio module's install/service scripts.
#
# Toybox/busybox-only: no python, no patchelf, no host machine involved -
# just `grep -aFbo` to find the byte offset of a NEEDED/SONAME string inside
# an ELF's string table, and `dd` to overwrite it in place. This only works
# because every replacement name here is deliberately the SAME byte length
# as the string it replaces (libssl.so -> libssx.so, libcrypto.so ->
# libcryptx.so): a same-length swap needs no section growth and no offset
# recalculation, none of the complexity patchelf's general-purpose machinery
# exists to handle. Verified independently against patchelf/readelf output
# on a real device before this went anywhere near a module.
#
# Why the renamed libs are needed at all: a privileged/system app gets a
# linker namespace that chains through to /system/lib after its own
# directory, unlike a normal app's fully isolated one. If LedFx's bundled
# OpenSSL keeps the stock libssl.so/libcrypto.so names, the linker can
# silently resolve those NEEDED entries against the system's own BoringSSL
# libs instead (a real API fork, not just a version skew - confirmed via
# missing symbols like UINT32_it) and crash with a symbol lookup failure.
# Renaming sidesteps the collision entirely rather than fighting it.

# patch_elf_string <file> <old> <new>
#
# Overwrites every occurrence of <old> with <new> inside <file>. <old> and
# <new> MUST be the same byte length - this function refuses to run
# otherwise, since a length mismatch is exactly the case this whole
# same-length approach exists to avoid needing to handle.
#
# No-ops (returns 1, no error) if <old> is not found at all. That is what
# makes this safe to call unconditionally on every boot: the second and
# every subsequent call on an already-patched file is just a fast, silent
# no-op, not a failure.
patch_elf_string() {
  f="$1"; old="$2"; new="$3"
  if [ "${#old}" != "${#new}" ]; then
    echo "patch_elf_string: length mismatch ($old vs $new), refusing" >&2
    return 2
  fi
  found=0
  while :; do
    offset=$(grep -aFbo "$old" "$f" 2>/dev/null | head -1 | cut -d: -f1)
    [ -z "$offset" ] && break
    printf '%s' "$new" | dd of="$f" seek="$offset" oflag=seek_bytes conv=notrunc status=none 2>/dev/null
    found=1
  done
  [ "$found" = "1" ]
}

# patch_ssl_libs <dir>
#
# Applies the full set of renames needed for one directory containing
# libssl.so/libcrypto.so and their consumers (libpython3.14.so,
# libpythonbin.so). Renames the files themselves too, not just their
# internal SONAME - the linker resolves NEEDED entries by filename lookup,
# not by scanning directory contents for a matching internal soname field,
# so the on-disk name has to match what the patched consumers now ask for.
patch_ssl_libs() {
  dir="$1"
  [ -f "$dir/libssl.so" ] || return 0   # already renamed on a prior run

  patch_elf_string "$dir/libssl.so"        "libssl.so"    "libssx.so"
  patch_elf_string "$dir/libssl.so"        "libcrypto.so" "libcryptx.so"
  patch_elf_string "$dir/libcrypto.so"     "libcrypto.so" "libcryptx.so"
  patch_elf_string "$dir/libpython3.14.so" "libssl.so"    "libssx.so"
  patch_elf_string "$dir/libpython3.14.so" "libcrypto.so" "libcryptx.so"
  patch_elf_string "$dir/libpythonbin.so"  "libssl.so"    "libssx.so"
  patch_elf_string "$dir/libpythonbin.so"  "libcrypto.so" "libcryptx.so"

  mv -f "$dir/libssl.so"    "$dir/libssx.so"
  mv -f "$dir/libcrypto.so" "$dir/libcryptx.so"
}
