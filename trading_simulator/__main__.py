"""Enables `python -m trading_simulator ...` as the primary CLI entry point.

(`python -m trading_simulator.cli.main` also works, but triggers a Python
runpy RuntimeWarning because `trading_simulator.cli`'s own __init__ already
imports the `main` submodule as a side effect of `from .main import main`;
harmless, but noisy. This is the clean entry point -- along with the
`trading-simulator` console script installed by `pip install -e .`.)
"""
from .cli.main import main

if __name__ == "__main__":
    main()
