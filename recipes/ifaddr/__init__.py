from pythonforandroid.recipe import PythonRecipe


class IfaddrRecipe(PythonRecipe):
    """
    This recipe builds the python binding for the ifaddr library with a patch
    to change the library search name from libc.so to None. See comment in patch.diff
    for details.
    """

    name = 'ifaddr'
    version = '0.1.7'
    url = 'https://github.com/pydron/ifaddr/archive/{version}.tar.gz'
    md5 = 'dff6fabaf39fe5b25128ea4b10b26640'
    depends = ['setuptools']
    patches = ['patch.diff']

    call_hostpython_via_targetpython = False


recipe = IfaddrRecipe()
