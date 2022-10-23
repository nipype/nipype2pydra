import versioneer
from setuptools import setup, find_packages

PACKAGE_NAME = 'nipype2pydra'

INSTALL_REQUIRES = []
TESTS_REQUIRE = []
DEV_REQUIRE = []

PYTHON_VERSIONS = ["3.8", "3.9", "3.10"]

setup(
    name=PACKAGE_NAME,
    version=versioneer.get_version(),
    author="Thomas G. Close",
    author_email="tom.g.close@gmail.com",
    packages=find_packages(exclude=["tests", "test"]),
    url="https://github.com/australian-imaging-service/nipype2pydra",
    license="Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License",
    description=("Abstraction of Repository-Centric ANAlysis framework"),
    long_description=open("README.rst").read(),
    install_requires=INSTALL_REQUIRES,
    tests_require=TESTS_REQUIRE,
    entry_points={
        "console_scripts": [
            "arcana=arcana.cli:cli",
            "run-arcana-pipeline=arcana.cli.deploy:run_pipeline",
        ]
    },
    extras_require={"test": TESTS_REQUIRE, "dev": DEV_REQUIRE},
    cmdclass=versioneer.get_cmdclass(),
    classifiers=(
        [
            "Development Status :: 4 - Beta",
            "Intended Audience :: Healthcare Industry",
            "Intended Audience :: Science/Research",
            "License :: OSI Approved :: Apache Software License",
            "Natural Language :: English",
            "Topic :: Scientific/Engineering :: Bio-Informatics",
            "Topic :: Scientific/Engineering :: Medical Science Apps.",
        ]
        + ["Programming Language :: Python :: " + str(v) for v in PYTHON_VERSIONS]
    ),
    keywords="repository analysis neuroimaging workflows pipelines",
)
