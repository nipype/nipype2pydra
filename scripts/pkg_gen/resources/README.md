# Pydra task package for CHANGEME

This package contains a collection of Pydra task interfaces for CHANGEME. The basis of
which have been semi-automatically converted from the corresponding [Nipype](https://github.com/nipy/nipype)
interfaces. 

## Automatically-generated vs manually-curated tasks

Automatically generated tasks can be found in the `pydra.tasks.CHANGEME.auto` package.
These packages should be treated with extreme caution as they likely do not pass testing.
Generated tasks that have been edited and pass testing are imported into one or more of the
`pydra.tasks.CHANGEME.v*` packages, corresponding to the version of the CHANGEME toolkit
they are designed for. 

## Tests

This package comes with a battery of automatically generated test modules. To install
the necessary dependencies to run the tests

```
pip install -e .[test]
```

Then the tests, including [doctests](https://docs.python.org/3/library/doctest.html), can be launched using

```
pytest --doctest-modules pydra/tasks/*
```

By default, the tests are set to time-out after 10s, after which the underlying tool is
assumed to have passed the validation/initialisation phase and we assume that it will
run to completion. To disable this and run the test(s) through to completion run

```
pytest --doctest-modules --timeout-pass 0 pydra/tasks/*
```

## Continuous integration

This template uses [GitHub Actions](https://docs.github.com/en/actions/) to run tests and
deploy packages to PYPI. New packages are built and uploaded when releases are created on
GitHub, or new releases of Nipype or the Nipype2Pydra conversion tool are released.
Releases triggered by updates to Nipype or Nipype2Pydra are signified by the `postN`
suffix where N = <nipype-version><nipype2pydra-version> with '.'s stripped, e.g.
`v0.2.3post185010` corresponds to the v0.2.3 tag of

# Contributing to this package

## For developers

Install repo in developer mode from the source directory. It is also useful to
install pre-commit to take care of styling via [black](https://black.readthedocs.io/):

```
pip install -e .[dev]
pre-commit install
```


