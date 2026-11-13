"""cache 层单测：真实 Redis + 降级行为（mock 故障）。"""
import pytest

from storage import cache

def test_cache_set_get_roundtrip():
    """真实 Redis：存取往返"""
    assert cache.cache_set("test:key1", "hello", ttl=60)
    assert cache.cache_get("test:key1") == "hello"

def test_cache_miss_returns_none():
    """不存在的键 → None"""
    assert cache.cache_get("test:不存在") is None

def test_incr_counter():
    """计数器：连续自增"""
    a = cache.incr_counter("test:counter")
    b = cache.incr_counter("test:counter")
    assert b == a + 1

def test_rate_limit_blocks_after_limit():
    """限流：超过 limit 后拒绝"""
    results = [cache.check_rate_limit("test:rate", limit=3, window=60) for _ in range(5)]
    assert results == [True, True, True, False, False]

def test_degraded_when_no_redis(monkeypatch):
    """降级：Redis 不可用时全部静默降级（核心契约！）"""
    monkeypatch.setattr(cache, "_get_client", lambda: None)
    assert cache.cache_get("k") is None
    assert cache.cache_set("k", "v") is False
    assert cache.incr_counter("k") == 0
    assert cache.check_rate_limit("k", limit=3) is True   # 限流降级方向是放行
