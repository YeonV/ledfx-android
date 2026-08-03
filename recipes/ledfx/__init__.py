"""
LedFX recipe for python-for-android
A few changes are required to use LedFX on Android:
  - All requirements must be listed in this recipe file because python-for-android doesn't install them from setup.py by default
  - Requirements that are not pure python need their own recipes to tell python-for-android how to compile it on android. Aubio is one example.
"""
from pythonforandroid.recipe import PyProjectRecipe


class LedFxRecipe(PyProjectRecipe):
    """
    This recipe instructs python-for-android how to build LedFx. The LedFx source is expected to be already located in deps/ledfx
    """
    name = 'ledfx'

    def check_prebuilt(self, arch, msg=""):
        """
        Never satisfy this recipe from PyPI.

        p4a's prebuilt lookup asks pip whether a wheel already exists and, if so,
        installs that instead of building. This recipe has no version pin (the
        source is whatever sits in deps/ledfx), so the query goes out as a bare
        `ledfx`, matches the pure-python py3-none-any wheel published on PyPI,
        and silently replaces the local checkout with an unrelated release.

        That shipped LedFx 2.0.90 inside a 2.1.6020 APK, which then died on
        import with "No module named 'pkg_resources'" and left the app hanging
        on the splash screen.
        """
        return False

    depends = [
        'numpy',
        'aiohttp',
        'aubio-ledfx',
        'zeroconf',
        'pybase64',
        'pillow',
        'samplerate-ledfx',
        'requests',
        'netifaces',
        'vnoise',
        # Imported at startup by ledfx/core.py. Has to be a recipe rather than a
        # python_depends entry - it declares requires-python <3.14 and pip would
        # reject it. See recipes/audio-hotplug/__init__.py.
        'audio-hotplug'
    ]
    
    python_depends = [
        'multidict>=6.4.3,<7',
        'sacn>=1.9.0,<2',
        'python-osc>=1.9.3,<2',
        'stupidartnet>=1.4.0,<2',
        'openrgb-python>=0.2.15,<1',
        'flux-led>=1.2.0,<2',
        'aiohttp-cors>=0.8.1,<1',
        'voluptuous>=0.14.1,<1',
        'paho-mqtt>=1.6.1,<2',
        'pyserial>=3.5,<4',
        'icmplib>=3.0.4,<4',
        'certifi>=2025.4.26,<2026',
        'python-dotenv>=1.1.0,<2',
        'webcolors>=24,<25',
        'packaging>=21,<22',
        'xled>=0.7.0',
        'lifx-async>=5.1.0'
    ]


recipe = LedFxRecipe()
