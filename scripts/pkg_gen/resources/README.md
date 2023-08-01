# Pydra task package for CHANGEME

This package contains a collection of Pydra task interfaces for CHANGEME. The basis for
which have been semi-automatically 

## Tests

This package comes with a default set of test modules, and we encourage users to use pytest.
Tests can be discovered and run using:

```
pytest --doctest-modules pydra/tasks/*
```

## Continuous integration

This template uses [GitHub Actions](https://docs.github.com/en/actions/) to run tests. To simulate
several plausible development or installation environments, we test over all Python versions
supported by Pydra, and install Pydra and the current package in both standard and
[editable](https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs) modes.

The combination of standard/editable is in particular designed to ensure that namespace packaging
does not break. We strongly recommend keeping these tests in place for this reason, as one
non-compliant package can potentially affect Pydra or other task packages.

In addition to verifying installations do not break or conflict, pytest is run on the package,
including all tests found in `test/` directories and [doctests].

Finally, packages are built and uploaded as artifacts for inspection. When a tag is pushed,
the packages are uploaded to PyPI if a valid [API token](https://pypi.org/help/#apitoken) is placed
in the [repository secrets](https://docs.github.com/en/actions/reference/encrypted-secrets).

[doctests]: https://docs.python.org/3/library/doctest.html

# Contributing to this package

## For developers

Install repo in developer mode from the source directory. It is also useful to
install pre-commit to take care of styling via [black](https://black.readthedocs.io/):

```
pip install -e .[dev]
pre-commit install
```


