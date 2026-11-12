from pythonforandroid.recipe import RustCompiledComponentsRecipe


class PydanticcoreRecipe(RustCompiledComponentsRecipe):
    version = "2.46.5"
    url = "https://github.com/pydantic/pydantic-core/archive/refs/tags/v{version}.tar.gz"
    sha256sum = "10416c15b8839ecc4ef4d0885da76da6fd0f67333a0eb8aff6d93c4b8f2910fc"
    site_packages_name = "pydantic_core"


recipe = PydanticcoreRecipe()
