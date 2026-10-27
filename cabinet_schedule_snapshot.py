"""Memoize schedule reads only within one read-only report/request.

No time-based cache: a subsequent request always sees committed transfers.
No writes, campaign changes, or changes to assignment/eligibility rules.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import sys
from threading import RLock

_snapshot = ContextVar('ege_cabinet_schedule_snapshot', default=None)
_lock = RLock()


def _memoize(module, name):
    original = getattr(module, name, None)
    if original is None or getattr(original, '_ege_schedule_memo', False):
        return
    @wraps(original)
    def cached(*args, **kwargs):
        cache = _snapshot.get()
        if cache is None:
            return original(*args, **kwargs)
        key = (original, args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = original(*args, **kwargs)
        return cache[key]
    cached._ege_schedule_memo = True
    setattr(module, name, cached)


def _prepare():
    # Lesson transfer installs after rewards during startup; resolve lazily.
    with _lock:
        transfer = sys.modules.get('ege11_lesson_transfer')
        if transfer is not None:
            for name in ('_effective_dates', '_effective_track', '_effective_sunday'):
                _memoize(transfer, name)
        deadlines = sys.modules.get('homework_deadline_logic')
        if deadlines is not None:
            _memoize(deadlines, 'due_lesson_for_source')


@contextmanager
def read_snapshot():
    _prepare()
    if _snapshot.get() is not None:
        yield
        return
    token = _snapshot.set({})
    try:
        yield
    finally:
        _snapshot.reset(token)


def _scope(module, name):
    original = getattr(module, name, None)
    if original is None or getattr(original, '_ege_schedule_scope', False):
        return
    @wraps(original)
    def scoped(*args, **kwargs):
        with read_snapshot():
            return original(*args, **kwargs)
    scoped._ege_schedule_scope = True
    setattr(module, name, scoped)


def install():
    with _lock:
        for module_name, function in (
            ('kulek_rewards', 'month_payload'),
            ('ege_admin_webapp', '_view'),
            ('ege_student_webapp', '_payload'),
        ):
            module = sys.modules.get(module_name)
            if module is None or not callable(getattr(module, function, None)):
                raise RuntimeError('CABINET_SNAPSHOT_REQUIRED_MODULE_MISSING')
            _scope(module, function)
    print('Cabinet schedule snapshot ready: request scoped; no persistent cache', flush=True)
