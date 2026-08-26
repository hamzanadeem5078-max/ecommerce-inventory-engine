import time
from fastapi import Request, HTTPException, status
from redis_db import redis_client

async def rate_limit_guard(request: Request):
    client_ip = request.client.host
    current_time = time.time()
    
    window_seconds = 10
    max_requests = 5
    cutoff_time = current_time - window_seconds
    
    # Step 2: Wipe stamps older than cutoff window
    await redis_client.zremrangebyscore(f"rate_limit:{client_ip}", 0, cutoff_time)
    
    # Step 3: Count remaining valid stamps
    request_count = await redis_client.zcard(f"rate_limit:{client_ip}")
    
    # Step 4: Block or Allow
    if request_count >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
        
    # Add new stamp & reset TTL
    await redis_client.zadd(f"rate_limit:{client_ip}", {str(current_time): current_time})
    await redis_client.expire(f"rate_limit:{client_ip}", window_seconds)