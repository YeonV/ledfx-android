from pythonforandroid.recipe import MesonRecipe


class AubioLedfxRecipe(MesonRecipe):

    meson_version = "1.9.1"

    # aubio's python/meson.build does find_installation('python3', modules: ['numpy']),
    # which runs p4a's wrapper script - i.e. hostpython with the target sysconfig
    # faked. So numpy has to be importable by *hostpython*; the cross-compiled
    # numpy installed for Android is not.
    #
    # This used to work by accident: p4a's numpy recipe listed numpy in its own
    # hostpython_prerequisites, and because that attribute was a shared mutable
    # class list, the entry leaked into every recipe that did not define one.
    # Upstream dropped that list and the leak is now fixed, so declare it here -
    # the same way upstream's scipy recipe does.
    hostpython_prerequisites = ["numpy"]

    version = "v0.4.11"
    url = "https://github.com/ledfx/aubio-ledfx/archive/{version}.zip"
    depends = ["numpy"]


recipe = AubioLedfxRecipe()
