from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from database import Base, engine
import dependencies
import models
import redis_db
from routers import categories, health, inventory, orders, products

# Fires the machinery to look at models and build them in Postgres
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Safely close connection for async redis pool
    await redis_db.redis_client.aclose()


# Global rate limiter dependency wrapper for FastAPI
async def global_rate_limiter(request: Request):
    client_ip = request.client.host if request.client else "anonymous"

    # Enforce limit using module-level dot notation with async context manager
    async with dependencies.rate_limit_guard(
        key=f"global:{client_ip}",
        limit=60,
        window=60,
        client=redis_db.get_redis_client(),
    ):
        pass


# Initialize FastAPI with global rate limiting dependency
app = FastAPI(lifespan=lifespan, dependencies=[Depends(global_rate_limiter)])

# Include routers
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(orders.router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}


@app.get("/redis-test")
async def test_redis():
    client = redis_db.get_redis_client()
    await client.set("engine_status", "operational")
    val = await client.get("engine_status")
    return {"redis_status": val}


@app.get("/test-rate-limit")
async def test_rate_limit():
    return {"message": "Access granted!"}