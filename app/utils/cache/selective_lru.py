"""Bounded, thread-safe LRU for single-argument lookups with targeted eviction."""

from collections import OrderedDict, namedtuple
from functools import wraps
from threading import RLock

_CacheInfo = namedtuple("CacheInfo", "hits misses maxsize currsize")


def selective_lru_cache(maxsize=1024):
    def decorate(loader):
        entries = OrderedDict()
        lock = RLock()
        hits = misses = 0

        @wraps(loader)
        def lookup(key):
            nonlocal hits, misses
            # Serialize a miss with invalidation so an old result cannot be
            # published after the corresponding file has been invalidated.
            with lock:
                if key in entries:
                    hits += 1
                    entries.move_to_end(key)
                    return entries[key]
                misses += 1
                value = loader(key)
                entries[key] = value
                while len(entries) > maxsize:
                    entries.popitem(last=False)
                return value

        def invalidate(predicate):
            with lock:
                for key, value in list(entries.items()):
                    if predicate(key, value):
                        del entries[key]

        def clear():
            nonlocal hits, misses
            with lock:
                entries.clear()
                hits = misses = 0

        def info():
            with lock:
                return _CacheInfo(hits, misses, maxsize, len(entries))

        lookup.cache_clear = clear
        lookup.cache_info = info
        lookup.cache_invalidate = invalidate
        return lookup

    return decorate
