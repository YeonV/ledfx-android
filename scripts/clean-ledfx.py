# Force full rebuild of ledfx by deleting all relevant build artifacts

import pathlib
import shutil

root = pathlib.Path(__file__).parent.parent
build_root = root / '.buildozer'

patterns = [
    'android/platform/build-*/build/other-builds/ledfx',
    'android/platform/build-*/build/python-installs/ledfx/*/ledfx*',
    'android/platform/build-*/packages/ledfx',
    'android/platform/build-*/dists'
]

for p in patterns:
    for d in build_root.rglob(p):
        shutil.rmtree(d, ignore_errors=True)
