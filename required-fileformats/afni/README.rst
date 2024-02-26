How to customise this template
==============================

#. Rename the `related-packages/fileformats/afni` directory to the name of the fileformats subpackage (e.g. `medimage_fsl`)
#. Search and replace "afni" with the name of the fileformats subpackage the extras are to be added
#. Replace name + email placeholders in `pyproject.toml` for developers and maintainers
#. Add the extension file-format classes
#. Ensure that all the extension file-format classes are imported into the extras package root, i.e. `fileformats/afni`
#. Delete these instructions

...

FileFormats Extension - afni
====================================
.. image:: https://github.com/nipype/pydra-afni/actions/workflows/ci-cd.yml/badge.svg
    :target: https://github.com/nipype/pydra-afni/actions/workflows/ci-cd.yml

This is the "afni" extension module for the
`fileformats <https://github.com/ArcanaFramework/fileformats-core>`__ package


Quick Installation
------------------

This extension can be installed for Python 3 using *pip*::

    $ pip3 install fileformats-afni

This will install the core package and any other dependencies

License
-------

This work is licensed under a
`Creative Commons Attribution 4.0 International License <http://creativecommons.org/licenses/by/4.0/>`_

.. image:: https://i.creativecommons.org/l/by/4.0/88x31.png
  :target: http://creativecommons.org/licenses/by/4.0/
  :alt: Creative Commons Attribution 4.0 International License
