"""Redis 缓存层：会话热缓存 + 计数器 + 限流（Phase 5）。

降级原则（架构红线）：Redis 挂了/没配 REDIS_URL，所有函数静默降级
（返回 None/False/0），绝不抛异常——Redis 是加速层不是必需依赖，
它挂了系统必须照常工作（直查 PG）。
"""
import os

import redis

_client = None

def _get_client():
    """惰性单例连接。REDIS_URL 未配置或连接失败 → None（降级信号）。"""
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL")
        if not url:
            return None
        try:
            client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
            client.ping()
            _client = client
        except redis.RedisError:
            return None          # 连不上 → 永久降级（本进程内）
    return _client

def cache_get(key: str) -> str | None:
    """取缓存。Redis 不可用 → None（调用方回退查 PG）。"""
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except redis.RedisError:
        return None

def cache_set(key: str, value: str, ttl: int = 300) -> bool:
    """写缓存（默认 5 分钟过期）。Redis 不可用 → False。"""
    client = _get_client()
    if client is None:
        return False
    try:
        client.set(key, value, ex=ttl)
        return True
    except redis.RedisError:
        return False

def incr_counter(key: str) -> int:
    """计数器 +1（降级率/检空率/限流计数）。Redis 不可用 → 0。"""
    client = _get_client()
    if client is None:
        return 0
    try:
        return client.incr(key)
    except redis.RedisError:
        return 0

def check_rate_limit(key: str, limit: int, window: int = 60) -> bool:
    """滑动窗口限流：window 秒内超过 limit 次 → False（拒绝）。

    实现：INCR 计数 + 首次 EXPIRE 设置窗口。Redis 不可用 → True（放行）。
    降级方向注意：缓存降级是「返回 None 让调用方回退」，限流降级是
    「放行」——Redis 挂了不能把用户全拦在门外。
    """
    client = _get_client()
    if client is None:
        return True
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)
        return count <= limit
    except redis.RedisError:
        return True              # 降级方向：故障时放行
