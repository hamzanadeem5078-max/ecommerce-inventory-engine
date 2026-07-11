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