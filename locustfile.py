# locustfile.py
import random
import uuid
from locust import HttpUser, task, between

class FlashSaleUser(HttpUser):
    # Simulate realistic human think-time between 0.5 and 2 seconds
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Executed when a virtual user starts up."""
        self.product_id = random.randint(1, 10) # Assuming product IDs 1-10 exist
        
    def _get_w3c_traceparent(self) -> dict:
        """Generate a valid W3C traceparent header for distributed tracing telemetry."""
        trace_id = uuid.uuid4().hex
        parent_id = uuid.uuid4().hex[:16]
        # Format: version (00) - trace_id (32 hex) - parent_id (16 hex) - trace_flags (01)
        return {"traceparent": f"00-{trace_id}-{parent_id}-01"}

    @task(3)
    def browse_products(self):
        """Simulate organic traffic browsing the product catalog with trace propagation."""
        headers = self._get_w3c_traceparent()
        self.client.get(
            "/products/",
            headers=headers,
            name="/products (Browse)"
        )

    @task(1)
    def execute_flash_sale_order(self):
        """Simulate high-concurrency flash sale checkout hammering with trace propagation."""
        headers = self._get_w3c_traceparent()
        payload = {
            "product_id": self.product_id,
            "quantity": 1
        }
        with self.client.post(
            "/orders/", 
            json=payload, 
            headers=headers,
            name="/orders (Flash Sale Buy)",
            catch_response=True
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate-limited by global IP guard")
            elif response.status_code == 400:
                # Stock out is expected under high concurrency flash sales
                response.success()
            else:
                response.failure(f"Unexpected status code: {response.status_code}")