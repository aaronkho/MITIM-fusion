from setuptools import setup, find_packages
from src.mitim_tools import __version__

'''
Note that this MITIM package was tested with gacode:
    branch:     mit_development
    commit:     d18993ddbc51139b5a143375280b6cea5a882c0b
'''

setup(
    name="MITIM",
    version=__version__,
    description="MIT Integrated Modeling Suite for Fusion Applications",
    url="https://mitim-fusion.readthedocs.io/",
    author="P. Rodriguez-Fernandez",
    author_email="pablorf@mit.edu",
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "pip",
        "numpy<2.0", # Some issue happened with 2.0.0
        "matplotlib",
        "argparse",
        "h5py",
        "netCDF4",
        "xarray==2022.6.0", # This is a compromise between the requirements of omfit_classes (fails for high versions) and the PLASMAstate xr reader (importlib_metadata issues)
        "pandas",
        "xlsxwriter",
        "statsmodels",
        "dill",
        "IPython",
        "pyDOE",
        "multiprocessing_on_dill",
        "deap",
        "paramiko",
        "tqdm",
        "botorch==0.9.4",  # Comes w/ gpytorch==1.11, torch>=1.13.1. PRF also tested w/ torch-2.3.0
        "scikit-image",  # Stricly not for MITIM, but good to have for pygacode
    ],
    extras_require={
        "pyqt": "PyQt6",
        "omfit": [
            "omfit_classes",
            "matplotlib==3.5.3",  # As of 12/07/2023, omfit_classes fails for higher versions
            "omas",
            "fortranformat",
            "openpyxl",
        ],
        "freegs": [
            "Shapely",
            "freegs @ git+https://github.com/bendudson/freegs.git",
        ],
    },
)
