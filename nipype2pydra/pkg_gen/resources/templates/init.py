"""
This is a basic doctest demonstrating that the package and pydra can both be successfully
imported.

>>> import pydra.engine
>>> import pydra.tasks.CHANGEME
"""

from warnings import warn
from pathlib import Path

pkg_path = Path(__file__).parent.parent

try:
    from ._version import __version__
except ImportError:
    raise RuntimeError(
        "pydra-CHANGEME has not been properly installed, please run "
        f"`pip install -e {str(pkg_path)}` to install a development version"
    )
if "post" not in __version__:
    try:
        from ._post_release import post_release
    except ImportError:
        try:
            # For interface-only packages
            from .auto._post_release import post_release
        except ImportError:
            pass
        warn(
            "Nipype interfaces haven't been automatically converted from their specs in "
            f"`nipype-auto-conv`. Please run `{str(pkg_path / 'nipype-auto-conv' / 'generate')}` "
            "to generated the converted Nipype interfaces in pydra.tasks.CHANGEME.auto"
        )
    else:
        __version__ += "post" + post_release


__all__ = ["__version__"]
