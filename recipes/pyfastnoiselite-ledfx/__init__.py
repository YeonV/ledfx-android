from pythonforandroid.recipe import PyProjectRecipe


class PyfastnoiseliteLedFxRecipe(PyProjectRecipe):
    version = "0.0.9"
    url = (
        "https://files.pythonhosted.org/packages/79/3b/"
        "1569011ff0a0c8cc3367e9638a532ed5b44ebfc9ec806cb44c6e85e7d850/"
        "pyfastnoiselite_ledfx-{version}.tar.gz"
    )
    sha256sum = "747ce100335acfd3a8c21c875009cef41c6e65095e2568e33940152ba2d5d0f5"
    python_depends = ["numpy>=2.0.0,<3.0.0"]


recipe = PyfastnoiseliteLedFxRecipe()
