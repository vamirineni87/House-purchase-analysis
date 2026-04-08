"""Auto-tracing for pipa modules.

Provides a `traced()` decorator that logs entry/exit/duration of any
sync or async function, plus `autotrace_module()` and `autotrace_package()`
walkers that apply the decorator to every public callable in a module
without us having to edit each file by hand.

Why: when the UI is "stuck loading" we need to know which function the
event loop is parked inside. With autotrace on, every function call logs
"→ pkg.mod.fn START" and "← pkg.mod.fn DONE Xms" — the last START
without a matching DONE is where execution is stuck.

Output volume control:
    - DEBUG-level for fast functions (<10ms)
    - INFO-level for medium functions (10ms - 1s)
    - WARNING-level for slow functions (>= SLOW_FN_MS)
    - Exceptions always log at ERROR with the duration

Skip rules — autotrace_module() does NOT wrap:
    - dunder methods (__init__, __repr__, etc.)
    - private functions (leading underscore) — can opt them in later
    - classes (we descend into their methods, not the class itself)
    - things that aren't actual callables defined in the target module
      (re-exports from other modules are skipped)
    - ORM model classes (Pydantic / SQLAlchemy declarative) — wrapping
      their methods often breaks descriptor protocols
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
import types
from typing import Any, Callable

# A function call slower than this is logged at WARNING.
SLOW_FN_MS = 1000

# Sentinel attribute set on wrapped functions so we don't double-wrap.
_TRACED_ATTR = "__pipa_traced__"

# Sentinel attribute on a function (or its module) to opt OUT of tracing.
_NO_TRACE_ATTR = "__pipa_no_trace__"


def traced(fn: Callable, *, log_args: bool = False) -> Callable:
    """Wrap a sync or async function with entry/exit/duration logging.

    The wrapped function looks up its logger by ``fn.__module__`` so log
    lines are filterable per-package.

    Set ``log_args=True`` to also log the call's positional args (truncated
    to 200 chars). Off by default since most call args are large dicts /
    sessions / pages.
    """
    if getattr(fn, _TRACED_ATTR, False):
        return fn  # already wrapped
    if getattr(fn, _NO_TRACE_ATTR, False):
        return fn  # opted out

    qualname = getattr(fn, "__qualname__", fn.__name__)
    log = logging.getLogger(fn.__module__)

    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            t0 = time.monotonic()
            if log_args:
                arg_summary = repr(args)[:200]
                log.debug("→ %s args=%s", qualname, arg_summary)
            else:
                log.debug("→ %s", qualname)
            try:
                result = await fn(*args, **kwargs)
            except Exception:
                ms = (time.monotonic() - t0) * 1000
                log.error("✗ %s FAILED after %.0fms", qualname, ms, exc_info=True)
                raise
            ms = (time.monotonic() - t0) * 1000
            if ms >= SLOW_FN_MS:
                log.warning("← %s SLOW %.0fms", qualname, ms)
            elif ms >= 10:
                log.info("← %s %.0fms", qualname, ms)
            else:
                log.debug("← %s %.0fms", qualname, ms)
            return result

        setattr(async_wrapper, _TRACED_ATTR, True)
        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args, **kwargs):
        t0 = time.monotonic()
        if log_args:
            arg_summary = repr(args)[:200]
            log.debug("→ %s args=%s", qualname, arg_summary)
        else:
            log.debug("→ %s", qualname)
        try:
            result = fn(*args, **kwargs)
        except Exception:
            ms = (time.monotonic() - t0) * 1000
            log.error("✗ %s FAILED after %.0fms", qualname, ms, exc_info=True)
            raise
        ms = (time.monotonic() - t0) * 1000
        if ms >= SLOW_FN_MS:
            log.warning("← %s SLOW %.0fms", qualname, ms)
        elif ms >= 10:
            log.info("← %s %.0fms", qualname, ms)
        else:
            log.debug("← %s %.0fms", qualname, ms)
        return result

    setattr(sync_wrapper, _TRACED_ATTR, True)
    return sync_wrapper


def no_trace(fn_or_class):
    """Decorator: mark a function or class as opted out of autotrace.

    Useful for hot-loop helpers, ORM models, Pydantic schemas where
    instrumentation either breaks descriptor protocols or floods the
    log.
    """
    setattr(fn_or_class, _NO_TRACE_ATTR, True)
    return fn_or_class


def _is_local_callable(obj: Any, target_module: str) -> bool:
    """True iff `obj` is a function/method DEFINED IN `target_module`.

    We use ``__module__`` to filter out re-exports — e.g. if a module
    does ``from foo import bar``, we don't want to wrap bar twice.
    """
    if not callable(obj):
        return False
    mod = getattr(obj, "__module__", None)
    if mod != target_module:
        return False
    return True


def _wrap_class_methods(cls: type, target_module: str) -> int:
    """Walk a class and wrap its methods. Returns number wrapped."""
    if getattr(cls, _NO_TRACE_ATTR, False):
        return 0
    if not isinstance(cls, type):
        return 0
    # Skip ORM model bases / Pydantic models — wrapping their methods
    # often breaks SQLAlchemy descriptors and Pydantic field validators.
    for skip_base in ("DeclarativeBase", "Base", "BaseModel"):
        if any(b.__name__ == skip_base for b in cls.__mro__[1:]):
            return 0

    wrapped = 0
    for name, attr in list(cls.__dict__.items()):
        # Skip dunders
        if name.startswith("__") and name.endswith("__"):
            continue

        # Plain function on a class becomes a method
        if isinstance(attr, types.FunctionType):
            if _is_local_callable(attr, target_module):
                setattr(cls, name, traced(attr))
                wrapped += 1
            continue

        # @staticmethod
        if isinstance(attr, staticmethod):
            inner = attr.__func__
            if _is_local_callable(inner, target_module):
                setattr(cls, name, staticmethod(traced(inner)))
                wrapped += 1
            continue

        # @classmethod
        if isinstance(attr, classmethod):
            inner = attr.__func__
            if _is_local_callable(inner, target_module):
                setattr(cls, name, classmethod(traced(inner)))
                wrapped += 1
            continue
    return wrapped


def autotrace_module(module: types.ModuleType) -> int:
    """Apply traced() to every public callable defined in `module`.

    Returns total count wrapped (functions + class methods). Safe to
    call repeatedly — already-wrapped callables are skipped.
    """
    if getattr(module, _NO_TRACE_ATTR, False):
        return 0

    target_name = module.__name__
    wrapped = 0

    for name in dir(module):
        if name.startswith("_"):
            continue  # private/internal — skip
        obj = getattr(module, name, None)
        if obj is None:
            continue

        # Plain function defined in this module
        if isinstance(obj, types.FunctionType):
            if _is_local_callable(obj, target_name):
                setattr(module, name, traced(obj))
                wrapped += 1
            continue

        # Class defined in this module — wrap its methods
        if isinstance(obj, type):
            if obj.__module__ == target_name:
                wrapped += _wrap_class_methods(obj, target_name)

    return wrapped


def autotrace_package(package_prefix: str) -> int:
    """Auto-trace every loaded module whose name starts with `package_prefix`.

    Walks ``sys.modules`` so it only sees modules that have already been
    imported. Call this after the app's modules are loaded (e.g. inside
    the FastAPI lifespan startup, after route imports).

    Returns total count of callables wrapped.
    """
    import sys

    log = logging.getLogger("pipa.core.tracing")
    total = 0
    module_count = 0
    for name, mod in list(sys.modules.items()):
        if not name.startswith(package_prefix):
            continue
        if not isinstance(mod, types.ModuleType):
            continue
        try:
            count = autotrace_module(mod)
        except Exception:
            log.exception("autotrace failed for module %s", name)
            continue
        if count:
            module_count += 1
            total += count

    log.info("autotrace: wrapped %d callables across %d modules under %r",
             total, module_count, package_prefix)
    return total
