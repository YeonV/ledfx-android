"""
audio-hotplug recipe for python-for-android.

LedFx core imports this unconditionally at startup (`ledfx/core.py`:
`from audio_hotplug import create_monitor`), so without it the service dies on
import and the app hangs on the splash screen.

It cannot simply go in the ledfx recipe's `python_depends`. Those are resolved
by `process_python_modules()` with `--python-version <hostpython version>`,
which is 3.14.2, and audio-hotplug declares `requires-python ">=3.10,<3.14"` -
so pip refuses it. Worse, that resolution has no per-package error handling: a
single rejected requirement makes the whole call fail, and p4a merely warns and
returns *everything* unresolved.

Building from the sdist avoids all of that. `requires-python` is an installer
check, not a build-backend one, so `python -m build --wheel` produces the wheel
happily under 3.14 (verified locally against this exact sdist). The package is
pure python, so nothing is cross-compiled.
"""

from pythonforandroid.recipe import PyProjectRecipe


class AudioHotplugRecipe(PyProjectRecipe):

    name = 'audio-hotplug'
    version = '0.1.0'
    url = 'https://pypi.io/packages/source/a/audio-hotplug/audio_hotplug-{version}.tar.gz'
    md5 = 'd6d3076bcf6c600e0ec5cbfb11d54b99'

    def check_prebuilt(self, arch, msg=""):
        """
        Skip the prebuilt-wheel lookup.

        It would ask pip for `audio-hotplug==0.1.0` with --python-version 3.14.2
        and be refused on requires-python, which only wastes a network round
        trip - the answer is always "build it".
        """
        return False


recipe = AudioHotplugRecipe()
