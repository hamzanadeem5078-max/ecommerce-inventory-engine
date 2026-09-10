import asyncio
import httpx

async def test_rate_limiter():
    url = "http://127.0.0.1:8000/orders/"
    payload = {
        "product_id": 1,
        "quantity": 1
    }

    async with httpx.AsyncClient() as client:
        print("--- Testing Rate Limiter (Max 5 req / 10s) ---")
        for i in range(1, 8):
            try:
                response = await client.post(url, json=payload)
                print(f"Req #{i} -> Status: {response.status_code} | Body: {response.json()}")
            except Exception as e:
                print(f"Req #{i} -> Error: {e}")
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(test_rate_limiter())