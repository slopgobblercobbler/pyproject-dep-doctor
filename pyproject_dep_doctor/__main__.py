"""Entry point for python -m pyproject_dep_doctor."""

import sys
from pyproject_dep_doctor.cli import main

if __name__ == "__main__":
    sys.exit(main())
