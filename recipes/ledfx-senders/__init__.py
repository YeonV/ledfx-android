import sh

from pythonforandroid.logger import shprint
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

    def build_arch(self, arch):
        # The sdist's rust-toolchain.toml pins Rust 1.94.0, and cargo builds in
        # the source dir with that pin. RustCompiledComponentsRecipe adds the
        # Android target from p4a's own cwd, i.e. to the default toolchain only,
        # so the pinned one had no `core` for the target. Adding it from the
        # source dir applies the pin.
        self.check_host_deps()
        shprint(
            sh.rustup,
            "target",
            "add",
            self.RUST_ARCH_CODES[arch.arch],
            _cwd=self.get_build_dir(arch.arch),
        )
        super().build_arch(arch)


recipe = LedFxSendersRecipe()
