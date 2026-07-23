# Contributing

Thanks for considering a contribution. This project is a market simulator
used for research, strategy prototyping, and education -- not a production
trading system connected to a real venue -- so contributions that improve
correctness, test coverage, and clarity are especially welcome.

## Getting set up

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .
pytest
```

Optional integrations (sentiment trading, FIX, databases, event streaming,
Optuna/MLflow) are not required to run the test suite; install
`requirements-full.txt` only if you're working on those areas.

## Before opening a PR

- Add or update tests under `tests/` for any behavior change, especially
  anything touching the matching engine (price-time priority, self-trade
  prevention, TIF handling) or risk manager -- these are the modules where a
  silent regression is most expensive.
- Run `pytest` locally; CI runs the same suite.
- Keep changes focused. Large refactors are easier to review as a series of
  small, well-described commits than one giant diff.
- If you change public API behavior (constructor signatures, module
  locations), note it in `MIGRATION.md` so downstream users aren't surprised.

## Reporting bugs

Please include: the exact CLI invocation or code snippet, expected vs.
actual behavior, and your Python version. For anything involving the
matching engine, a minimal reproducing order sequence is enormously
helpful -- see `tests/test_matching_engine.py` for the style we use.

## Code style

Plain, explicit code over clever code. Prefer a few extra lines that are
obviously correct over a dense one-liner. Catch specific exceptions where
you can identify them; avoid bare `except Exception: pass` in new code --
if a failure is truly safe to ignore, log why at an appropriate level
instead of swallowing it silently.
