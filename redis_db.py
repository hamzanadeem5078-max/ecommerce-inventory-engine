import os
from redis.asyncio import ConnectionPool, Redis

# Create pool using an environment variable URL (Fallback: localhost)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Construct the pool object
pool = ConnectionPool.from_url(
    REDIS_URL, max_connections=10, decode_responses=True, protocol=2
)

# Instantiate the Redis client bound to that pool
redis_client = Redis(connection_pool=pool)


def get_redis_client():
    return redis_client