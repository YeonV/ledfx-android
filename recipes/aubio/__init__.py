from pythonforandroid.recipe import PyProjectRecipe


class AubioRecipe(PyProjectRecipe):
    
    # v0.5.0-alpha
    version = "152d681"  # use most recent commit hash because no v0.5 tag exists at this point
    url = "https://github.com/aubio/aubio/archive/{version}.zip"
    md5 = "81ed069e971f1001629d736030a3dd2e"
    depends = ["numpy", "setuptools"]
    patches = [
        'remove-external-deps.patch'  # removes macos platform specific cmake configs so cross compilation works from macos
    ]


recipe = AubioRecipe()
