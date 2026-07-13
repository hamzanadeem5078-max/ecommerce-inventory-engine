# High-Concurrency E-Commerce Inventory & Flash Sale Engine

A production-grade backend engine designed to handle extreme transaction surges, data consistency, and rapid state transitions during flash sales. Built from scratch applying advanced enterprise patterns.

## 🛠️ Tech Stack & Architecture (FreeCodeCamp FastAPI Blueprint)
* **Framework:** FastAPI (Asynchronous request handling)
* **Data Validation & Schemas:** Pydantic
* **Database Layer:** PostgreSQL
* **ORM:** SQLAlchemy (Object Relational Mapper)
* **Database Migrations:** Alembic
* **Security & Auth:** JWT Bearer Tokens & OAuth2

## 📝 Development Diary

### Day 1 & 2: The Department Store Gateway
* **What I did:** Initialized the Git architecture and built the minimal application entry point in `main.py` using FastAPI.
* **The Logic:** Think of `app = FastAPI()` as setting up the entire department store, including the front doors. When a customer walks in wanting to go to the front desk to get a welcome message, they are making a GET request. We route them using `@app.get("/")`. To handle what happens when they get to that desk, we create an asynchronous function called `root()`—the standard naming convention—which serves as the receptionist. The receptionist then returns exactly what they want inside a dictionary: `return {"message": "Welcome to the Flash Sale Engine!"}`. Keeping it unified in a single file ensures zero architectural noise while testing structural boundaries.

### Day 3: Breathing Life into the Dead Machine (The Uvicorn Power Grid)
* **What I did:** Verified the file system workspace execution paths and booted the Uvicorn ASGI server to expose the local application instance to incoming network traffic.
* **The Logic:** Right now, our FastAPI building is a dead machine—like a laptop without power. To wake it up, **Uvicorn** acts as our electricity source, the terminal is our charging cable, and hitting the `Enter` key serves as plugging into the wall socket. Before sending this current, we ensure we aren't plugging into the wrong room by running `dir` to look for `main.py` (and using `cd` if we need to switch rooms). Executing `uvicorn main:app --reload` bridges the gap, instantly registering our machine in the local neighborhood with a live address at `http://127.0.0.1:8000`. When 10,000 customers hit that address at the exact same moment with order envelopes in hand, Uvicorn serves as the high-speed transit gateway that sweeps them through the front doors and fires them directly to the targeted counter location (`/`), triggering our asynchronous reception function to safely return the JSON payload.

### Day 4: The Automated Store Turnstile & The Price Sentry
* **What I did:** Imported the Pydantic `BaseModel` architectural class to create our first strict data validation schema (`Product`) to guard our future add-product feature against malicious or malformed user inputs.
* **The Logic:** While `app = FastAPI()` built the physical doors to our store, it doesn't automatically inspect what customers are bringing inside. For a high-concurrency inventory engine, we can't manually inspect every single box arriving at the loading dock. Instead, we went to the **Security Blueprint Factory (Pydantic)** and pulled the **`BaseModel` blueprint** to forge an automated turnstile system: `class Product(BaseModel)`. This system acts as our ultimate inventory shield. First, it acts as a **Fraud Blocker**: if a client tries to sneak in a price of `"free"`, the turnstile locks shut instantly because it expects a precise mathematical float, spotting the illegal string before bad data ever touches our engine. Second, it is a **Shape-Shifter (Type Coercion)**: if an honest client sends the price as a text string `"19.99"`, it doesn't crash; it automatically converts it into a clean math decimal (`19.99`) for us. Finally, it acts as a **Data Exporter (Serialization)**: once the data clears inspection, this system grants the asset the power to instantly morph into standard Python dictionaries or JSON text later using `.model_dump()`, perfectly prepared to be shipped downstream to our PostgreSQL database.