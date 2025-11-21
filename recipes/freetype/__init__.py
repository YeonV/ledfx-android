from pythonforandroid.recipes.freetype import FreetypeRecipe


class FreetypeRecipePinned(FreetypeRecipe):
    """
    Custom FreeType recipe with alternative download mirror
    since download.savannah.gnu.org is unreliable
    """
    version = '2.14.1'
    
    # Use SourceForge mirror instead of Savannah
    url = 'https://sourceforge.net/projects/freetype/files/freetype2/{version}/freetype-{version}.tar.gz'


recipe = FreetypeRecipePinned()
