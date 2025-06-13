from pythonforandroid.recipe import PyProjectRecipe


class ZeroconfRecipe(PyProjectRecipe):
    name = 'zeroconf'
    version = '0.147.0'
    url = 'https://github.com/jstasiak/python-zeroconf/archive/{version}.tar.gz'
    md5 = 'bda4260e155ce7f5d24b9d831d7a0f09'
    depends = ['setuptools', 'ifaddr']


recipe = ZeroconfRecipe()
