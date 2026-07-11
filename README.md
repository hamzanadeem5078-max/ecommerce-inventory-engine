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

### Day 1: The Department Store Gateway
* **What I did:** Built the minimal application entry point in `main.py` using FastAPI.
* **The Logic:** Think of `app = FastAPI()` as setting up the entire department store, including the front doors. When a customer walks in wanting to go to the front desk to get a welcome message, they are making a GET request. We route them using `@app.get("/")`. To handle what happens when they get to that desk, we create an asynchronous function called `root()`—the standard naming convention—which serves as the receptionist. The receptionist then returns exactly what they want inside a dictionary: `return {"message": "Welcome to the Flash Sale Engine!"}`.

### Day 2: The Infrastructure & Stockrooms
* **What I did:** Integrated SQLAlchemy inside `main.py` to establish the infrastructure for our database connection.
* **The Logic:** Now that the department store has a front desk, it needs a backend inventory system and stockrooms to actually hold goods. 
  * `create_engine` acts as the physical delivery highway connecting our store directly to the main PostgreSQL warehouse (`flash_sale_db`).
  * `SessionLocal` is like assigning an individual store clerk to a customer. Every time a customer places an order or checks stock, this clerk opens a temporary ledger, processes that specific transaction cleanly so no two orders overlap, and closes the book when done.
  * `Base` is the master layout blueprint for our store shelves. Any new product category or inventory shelf we build later will copy this blueprint so the warehouse knows exactly where everything belongs.