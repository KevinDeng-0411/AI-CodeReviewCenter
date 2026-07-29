"""async Redis 客户端（对应 Java RedisConfig + StringRedisTemplate）。"""

import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> redis.Redis:
    """FastAPI 依赖。"""
    return redis_client
