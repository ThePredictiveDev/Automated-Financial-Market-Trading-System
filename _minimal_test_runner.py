"""Minimal pytest-compatible test runner for environments without network
access to install pytest. NOT part of the delivered package -- this file is
a sandbox-only verification shim; the real `pytest` (see requirements-dev.txt
and .github/workflows/ci.yml) is what should be used normally.
"""
import inspect
import logging
import math
import sys
import tempfile
import traceback
from pathlib import Path

try:
    import pytest  # noqa: F401
    HAVE_REAL_PYTEST = True
except ImportError:
    HAVE_REAL_PYTEST = False

    class Skipped(Exception):
        pass

    class _Approx:
        def __init__(self, expected, rel=1e-6, abs=1e-9):
            self.expected = expected
            self.rel = rel
            self.abs = abs

        def __eq__(self, other):
            return math.isclose(other, self.expected, rel_tol=self.rel, abs_tol=self.abs)

        def __repr__(self):
            return f"approx({self.expected})"

    class _Raises:
        def __init__(self, exc_type):
            self.exc_type = exc_type
            self.value = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                raise AssertionError(f"expected {self.exc_type} to be raised, nothing was raised")
            if not issubclass(exc_type, self.exc_type):
                return False
            self.value = exc_val
            return True

    def _fixture(func=None, **kwargs):
        if func is None:
            return _fixture
        func._is_fixture = True
        return func

    def _skip(reason=""):
        raise Skipped(reason)

    pytest_module = type(sys)("pytest")
    pytest_module.approx = _Approx
    pytest_module.raises = _Raises
    pytest_module.fixture = _fixture
    pytest_module.skip = _skip
    sys.modules["pytest"] = pytest_module
    import pytest  # noqa: F401,E402


class _CaplogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        record.message = record.getMessage()
        self.records.append(record)


class _Caplog:
    def __init__(self):
        self._handler = _CaplogHandler()
        self._root = logging.getLogger()
        self._prev_level = self._root.level
        self._root.addHandler(self._handler)
        self._root.setLevel(logging.DEBUG)

    @property
    def records(self):
        return self._handler.records

    def at_level(self, level):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield
        return _cm()

    def close(self):
        self._root.removeHandler(self._handler)
        self._root.setLevel(self._prev_level)


import importlib
import io
import contextlib
from collections import namedtuple


class _MonkeyPatch:
    """Minimal stand-in for pytest's monkeypatch fixture: supports both
    `setattr(obj, name, value)` and `setattr("dotted.path", value)`."""

    _MISSING = object()

    def __init__(self):
        self._undo = []  # list of (obj, name, original_or_MISSING)

    def setattr(self, target, name_or_value, value=_MISSING):
        if value is self._MISSING:
            # two-arg form: target is a dotted string "module.sub.attr"
            dotted, val = target, name_or_value
            module_path, attr = dotted.rsplit(".", 1)
            obj = importlib.import_module(module_path) if module_path not in ("builtins",) else __import__("builtins")
            name = attr
            val_to_set = val
        else:
            obj, name, val_to_set = target, name_or_value, value
        original = getattr(obj, name, self._MISSING)
        self._undo.append((obj, name, original))
        setattr(obj, name, val_to_set)

    def undo(self):
        for obj, name, original in reversed(self._undo):
            if original is self._MISSING:
                delattr(obj, name)
            else:
                setattr(obj, name, original)
        self._undo.clear()


_ReadOuterr = namedtuple("ReadOuterr", ["out", "err"])


class _Capsys:
    def __init__(self):
        self._out = io.StringIO()
        self._err = io.StringIO()
        self._ctx = contextlib.redirect_stdout(self._out)
        self._ctx.__enter__()
        self._ctx_err = contextlib.redirect_stderr(self._err)
        self._ctx_err.__enter__()

    def readouterr(self):
        out, err = self._out.getvalue(), self._err.getvalue()
        self._out.truncate(0)
        self._out.seek(0)
        self._err.truncate(0)
        self._err.seek(0)
        return _ReadOuterr(out, err)

    def close(self):
        self._ctx.__exit__(None, None, None)
        self._ctx_err.__exit__(None, None, None)


def resolve_fixture(module, name, teardowns):
    if name == "tmp_path":
        d = tempfile.mkdtemp()
        return Path(d)
    if name == "caplog":
        cl = _Caplog()

        def _gen():
            yield cl
            cl.close()
        gen = _gen()
        value = next(gen)
        teardowns.append(gen)
        return value
    if name == "monkeypatch":
        mp = _MonkeyPatch()

        def _gen():
            yield mp
            mp.undo()
        gen = _gen()
        value = next(gen)
        teardowns.append(gen)
        return value
    if name == "capsys":
        cs = _Capsys()

        def _gen():
            yield cs
            cs.close()
        gen = _gen()
        value = next(gen)
        teardowns.append(gen)
        return value
    fn = getattr(module, name, None)
    if fn is None:
        raise RuntimeError(f"no fixture named {name!r} found in {module.__name__}")
    if inspect.isgeneratorfunction(fn):
        gen = fn()
        value = next(gen)
        teardowns.append(gen)
        return value
    return fn()


def run_module(path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    results = []
    for name in dir(module):
        if not name.startswith("test_"):
            continue
        fn = getattr(module, name)
        if not inspect.isfunction(fn):
            continue
        sig = inspect.signature(fn)
        teardowns = []
        try:
            kwargs = {p: resolve_fixture(module, p, teardowns) for p in sig.parameters}
            fn(**kwargs)
            results.append((name, "PASS", None))
        except Exception as exc:
            if not HAVE_REAL_PYTEST and type(exc).__name__ == "Skipped":
                results.append((name, "SKIP", str(exc)))
            else:
                results.append((name, "FAIL", traceback.format_exc()))
        finally:
            for gen in teardowns:
                try:
                    next(gen, None)
                except Exception:
                    pass
    return results


def main():
    root = Path(__file__).parent / "tests"
    total, failed, skipped = 0, 0, 0
    for path in sorted(root.glob("test_*.py")):
        for name, status, detail in run_module(path):
            total += 1
            print(f"{status}  {path.name}::{name}" + (f"  ({detail})" if status == "SKIP" else ""))
            if status == "FAIL":
                failed += 1
                print(detail)
            elif status == "SKIP":
                skipped += 1
    passed = total - failed - skipped
    print(f"\n{passed}/{total} passed, {skipped} skipped" + (f", {failed} FAILED" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
