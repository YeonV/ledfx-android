from pythonforandroid.recipe import RustCompiledComponentsRecipe


class PydanticcoreRecipe(RustCompiledComponentsRecipe):
    version = "2.46.5"
    url = (
        "https://files.pythonhosted.org/packages/af/f9/"
        "8a06bea35ef8daf588f707784c973a7046e0034c8d8cfb08828eeffb8b75/"
        "pydantic_core-{version}.tar.gz"
    )
    sha256sum = "10416c15b8839ecc4ef4d0885da76da6fd0f67333a0eb8aff6d93c4b8f2910fc"
    site_packages_name = "pydantic_core"

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        # maturin cannot always infer the API level from the target and stops
        # with "Failed to determine Android API level" (seen on armeabi-v7a).
        env["ANDROID_API_LEVEL"] = str(self.ctx.ndk_api)
        return env


recipe = PydanticcoreRecipe()
