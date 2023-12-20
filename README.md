MITIM: a toolbox for modeling tasks in plasma physics and fusion energy
=======================================================================

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![py3comp](https://img.shields.io/badge/py3-compatible-brightgreen.svg)](https://img.shields.io/badge/py3-compatible-brightgreen.svg)

The MITIM (MIT Integrated Modeling) is a versatile and user-friendly Python library designed for plasma physics and fusion energy researchers. This light-weight, command-line, object-oriented toolbox streamlines the execution and interpretation of physics models and simplifies complex optimization tasks.

Do not forget to visit the [Read-The-Docs](https://mitim-fusion.readthedocs.io).

Instructions
------------

In a nutshell:

1. Clone repository:
    ```bash
     git clone git@github.com:pabloprf/MITIM-fusion.git
    ```

2. Add path to *.bashrc* file and source mitim:
    ```bash
    export MITIM_PATH=/path/to/mitim/
    source $MITIM_PATH/config/mitim.bashrc
    ```
   
3. Install MITIM (``python3.9`` required):
    ```bash
    pip install -e $MITIM_PATH[pyqt,omfit]
    ```

References
----------

P. Rodriguez-Fernandez, N.T. Howard and J. Candy, [`Nonlinear gyrokinetic predictions of SPARC burning plasma profiles enabled by surrogate modeling](https://iopscience.iop.org/article/10.1088/1741-4326/ac64b2), Nucl. Fusion 62, 076036 (2022).

Documentation
-------------

Full documentation, including detailed installation instructions, FAQ and examples: [Documentation](https://mitim-fusion.readthedocs.io).