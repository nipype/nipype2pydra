"""
This is a basic doctest demonstrating that the package and pydra can both be successfully
imported.

>>> import pydra.engine
>>> import pydra.tasks.freesurfer
"""
try:
    from ._version import __version__ as main_version
except ImportError:
    pass

from .auto._version import auto_version  # Get version of 

if ".dev" in main_version:
    main_version, dev_version = main_version.split(".dev")
else:
    dev_version = None

__version__ = main_version + "." + auto_version
if dev_version:
    __version__ += ".dev" + dev_version
