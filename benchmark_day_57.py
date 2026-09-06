import asyncio
import time
import logging
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("benchmark")

# -----------------------------------------------------------------------------
# BLOCK 1: BOUNDED PRODUCER BURST GENERATOR
# -----------------------------------------------------------------------------
async def generate_event_burst(
    redis: Redis, 
    total_events: int = 10_000, 
    batch_size: int = 1_000,
    stream_name: str = "orders:events"
) -> dict:
    """
    Generates a high-concurrency event burst using bounded Redis Pipelines
    with defensive retry logic to protect client memory and handle transient drops.
    """
    start_time = time.perf_counter()
    events_enqueued = 0
    pipe = redis.pipeline()

    for i in range(1, total_events + 1):
        payload = {
            "event_id": f"bench_{i}",
            "enqueued_at": str(time.time()),
            "action": "FLASH_SALE_ORDER"
        }
        pipe.xadd(stream_name, payload)

        # Flush batch when memory threshold is reached
        if i % batch_size == 0 or i == total_events:
            retries = 3
            backoff = 0.5
            while retries > 0:
                try:
                    await pipe.execute()
                    events_enqueued += (i % batch_size) or batch_size
                    break
                except (ConnectionError, TimeoutError) as e:
                    retries -= 1
                    logger.warning(f"Pipeline flush failed: {e}. Retrying in {backoff}s... ({retries} left)")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    if retries == 0:
                        logger.error("Pipeline retry limit exhausted. Pausing benchmark stream burst.")
                        raise e

    elapsed = time.perf_counter() - start_time
    throughput = events_enqueued / elapsed if elapsed > 0 else 0

    return {
        "events_enqueued": events_enqueued,
        "elapsed_seconds": round(elapsed, 4),
        "producer_throughput_eps": round(throughput, 2)
    }

# -----------------------------------------------------------------------------
# BLOCK 2: NON-BLOCKING CONSUMER DRAIN MONITOR
# -----------------------------------------------------------------------------
async def monitor_drain_performance(
    redis: Redis,
    stream_name: str = "orders:events",
    group_name: str = "orders_consumer_group",
    poll_interval_sec: float = 0.1,
    timeout_sec: float = 30.0
) -> dict:
    """
    Monitors consumer group lag and pending entries until the stream is fully drained
    or the safety timeout boundary is breached. Yields control explicitly to avoid CPU starvation.
    """
    start_time = time.perf_counter()
    peak_lag = 0
    
    while (time.perf_counter() - start_time) < timeout_sec:
        stream_len = await redis.xlen(stream_name)
        
        lag = 0
        pending = 0
        try:
            groups = await redis.xinfo_groups(stream_name)
            for g in groups:
                g_name = g.get("name") if isinstance(g, dict) else g[1]
                if (g_name.decode() if isinstance(g_name, bytes) else g_name) == group_name:
                    lag = g.get("lag", 0) if isinstance(g, dict) else g[11]
                    pending = g.get("pending", 0) if isinstance(g, dict) else g[5]
                    break
        except Exception:
            pass

        if lag > peak_lag:
            peak_lag = lag

        # DRAIN COMPLETE CONDITION: Stream is completely processed and no pending ACK entries
        if stream_len == 0 or (lag == 0 and pending == 0 and stream_len > 0):
            elapsed = time.perf_counter() - start_time
            return {
                "status": "COMPLETED",
                "drain_time_seconds": round(elapsed, 4),
                "peak_lag": peak_lag,
                "remaining_stream_len": stream_len,
                "remaining_pending": pending
            }

        # Non-blocking yield to allow worker tasks to execute
        await asyncio.sleep(poll_interval_sec)

    # TIMEOUT BOUNDARY BREACHED
    elapsed = time.perf_counter() - start_time
    return {
        "status": "TIMEOUT_EXCEEDED",
        "drain_time_seconds": round(elapsed, 4),
        "peak_lag": peak_lag,
        "remaining_stream_len": await redis.xlen(stream_name),
        "remaining_pending": pending
    }

# -----------------------------------------------------------------------------
# BLOCK 3: ORCHESTRATED SUITE RUNNER
# -----------------------------------------------------------------------------
async def run_benchmark_suite(total_events: int = 10_000, batch_size: int = 1_000):
    redis = Redis(host="localhost", port=6379, db=0, decode_responses=False)
    
    logger.info(f"--- STARTING DAY 57 BENCHMARK SUITE ({total_events} EVENTS) ---")
    
    # 1. Fire Producer Burst
    burst_result = await generate_event_burst(redis, total_events=total_events, batch_size=batch_size)
    logger.info(f"Burst Result: {burst_result}")

    # 2. Monitor Worker Consumer Group Drain Rate
    logger.info("Monitoring Consumer Group Drain Rate...")
    drain_result = await monitor_drain_performance(redis, poll_interval_sec=0.1, timeout_sec=45.0)
    logger.info(f"Drain Result: {drain_result}")

    # 3. Calculate Overall System Throughput
    if drain_result["status"] == "COMPLETED" and drain_result["drain_time_seconds"] > 0:
        overall_eps = total_events / drain_result["drain_time_seconds"]
        logger.info(f"SUCCESS: System processed at {round(overall_eps, 2)} Events/Sec (EPS)")
    else:
        logger.warning(f"BENCHMARK WARNING: Stream did not fully drain. State: {drain_result['status']}")

    await redis.close()

if __name__ == "__main__":
    asyncio.run(run_benchmark_suite(total_events=5_000, batch_size=500))