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