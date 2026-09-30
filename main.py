import uuid
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from database import Base, engine
import dependencies
import models
import redis_db
from routers import categories, health, inventory, orders, products, metrics_router, dlq

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = redis_db.get_redis_client()
    app.state.redis = client
    yield
    await client.close()


async def global_rate_limiter(request: Request):
    client_ip = request.client.host if request.client else "anonymous"
    redis_c = redis_db.get_redis_client()
    async with dependencies.rate_limit_guard(
        key=f"global:{client_ip}",
        limit=60,
        window=60,
        client=redis_c,
    ):
        pass


app = FastAPI(lifespan=lifespan, dependencies=[Depends(global_rate_limiter)])


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    incoming_id = request.headers.get("X-Correlation-ID")
    corr_id = incoming_id if incoming_id else str(uuid.uuid4())
    token = dependencies.correlation_id_var.set(corr_id)
    
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response
    finally:
        dependencies.correlation_id_var.reset(token)


app.include_router(categories.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(orders.router)
app.include_router(metrics_router.router)
app.include_router(dlq.router)

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