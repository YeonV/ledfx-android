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

    depends = [
        'numpy',
        'aiohttp',
        'aubio',
        'zeroconf',
        'pybase64',
        'pillow',
        'samplerate',
        'requests',
    ]
    
    python_depends = [
        'multidict>=6.0.4',
        'sacn>=1.9.0',
        'python-osc>=1.8.3',
        'stupidartnet>=1.4.0,<2.0.0',
        'openrgb-python>=0.2.15',
        'flux-led>=1.0.4',
        'aiohttp-cors>=0.7.0',
        'voluptuous>=0.14.1',
        'paho-mqtt>=1.6.1',
        'psutil>=5.9.7',
        'pyserial>=3.5',
        'icmplib>=3.0.4',
        'certifi>=2023.11.17',
        'python-dotenv>=1.0.0,<2.0.0',
        'vnoise>=0.1.0,<1.0.0',
        'webcolors>=24',
        'sentry-sdk>=1.40.4'
    ]


recipe = LedFxRecipe()
