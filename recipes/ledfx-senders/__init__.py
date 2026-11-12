from pythonforandroid.recipe import RustCompiledComponentsRecipe


class LedFxSendersRecipe(RustCompiledComponentsRecipe):
    version = "0.4.0"
    url = (
        "https://files.pythonhosted.org/packages/32/0b/"
        "cba8f7553968fc27baf406586375697fb6687b7d9bcc9edc4e54d0d22024/"
        "ledfx_senders-{version}.tar.gz"
    )
    sha256sum = "8b21dbc3d0037b4e09325472c565a913e4ac8e4ca1a64069bcc18e484b52f2d9"
    site_packages_name = "ledfx_senders"
    python_depends = ["numpy>=2.0.0,<3.0.0"]


recipe = LedFxSendersRecipe()
