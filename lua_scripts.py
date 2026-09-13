# lua_scripts.py or inline script definition
RESERVE_STOCK_LUA = """
local stock_key = KEYS[1]
local user_claims_key = KEYS[2]

local requested_qty = tonumber(ARGV[1])
local user_id = ARGV[2]

-- 1. Check if the stock key exists
local current_stock = redis.call('GET', stock_key)
if not current_stock then
    return -1 -- Error: Stock key does not exist / Flash sale inactive
end

current_stock = tonumber(current_stock)

-- 2. Check duplicate claim for user (Idempotency)
if redis.call('SISMEMBER', user_claims_key, user_id) == 1 then
    return -2 -- Error: User has already claimed stock
end

-- 3. Evaluate stock availability
if current_stock < requested_qty then
    return 0 -- Error: Insufficient stock
end

-- 4. Atomic Execution: Decrement stock and record claim
redis.call('DECRBY', stock_key, requested_qty)
redis.call('SADD', user_claims_key, user_id)

return 1 -- Success: Stock reserved
"""


ROLLBACK_STOCK_LUA = """
local stock_key = KEYS[1]
local user_claims_key = KEYS[2]

local quantity = tonumber(ARGV[1])
local user_id = ARGV[2]

-- 1. Restore the stock count
redis.call('INCRBY', stock_key, quantity)

-- 2. Remove user from claims set
redis.call('SREM', user_claims_key, user_id)

return 1
"""


SLIDING_WINDOW_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window

-- 1. Remove timestamps older than rolling sliding window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

-- 2. Count current active requests in window
local current_requests = redis.call('ZCARD', key)

-- 3. Check threshold limit
if current_requests >= max_limit then
    return 0 -- Rejected (Rate limit reached)
end

-- 4. Record new request timestamp with unique member
redis.call('ZADD', key, now, member)

-- 5. Refresh TTL so idle ZSET auto-expires from memory
redis.call('EXPIRE', key, window)

return 1 -- Allowed
"""