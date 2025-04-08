from pythonforandroid.recipe import PyProjectRecipe


class ZeroconfRecipe(PyProjectRecipe):
    name = 'zeroconf'
    version = '0.146.1'
    url = 'https://github.com/jstasiak/python-zeroconf/archive/{version}.tar.gz'
    md5 = '9a8a08184f942e6cae1384aef61f4ecb'
    depends = ['setuptools', 'ifaddr']


recipe = ZeroconfRecipe()
