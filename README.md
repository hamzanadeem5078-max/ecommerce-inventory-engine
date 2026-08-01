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
* **What I did:** Imported the Pydantic `BaseModel` architectural class to create our first data validation schema (`Product`) to guard our future add-product feature against malicious or malformed user inputs.
* **The Logic:** While `app = FastAPI()` built the physical doors to our store, it doesn't automatically inspect what customers are bringing inside. For a high-concurrency inventory engine, we can't manually inspect every single box arriving at the loading dock. Instead, we went to the **Security Blueprint Factory (Pydantic)** and pulled the **`BaseModel` blueprint** to forge an automated turnstile system: `class Product(BaseModel)`. This system acts as our ultimate inventory shield. First, it acts as a **Fraud Blocker**: if a client tries to sneak in a price of `"free"`, the turnstile locks shut instantly because it expects a precise mathematical float, spotting the illegal string before bad data ever touches our engine. Second, it is a **Shape-Shifter (Type Coercion)**: if an honest client sends the price as a text string `"19.99"`, it doesn't crash; it automatically converts it into a clean math decimal (`19.99`) for us. Finally, it acts as a **Data Exporter (Serialization)**: once the data clears inspection, this system grants the asset the power to instantly morph into standard Python dictionaries or JSON text later using `.model_dump()`, perfectly prepared to be shipped downstream to our PostgreSQL database.

### Day 5: The Specialized Product Intake Officer & The Auto-Instantiation Engine
* **What I did:** Implemented our first state-changing network boundary—a POST endpoint (`/product`) that dynamically ingests, validates, instantiates, and echoes back structured product data using our Pydantic schema as an asynchronous function parameter.
* **The Logic:** If our GET route was a general receptionist waving guests through the lobby, our `@app.post("/product")` route is a **specialized product intake officer** stationed at the loading dock. When a client (like Postman) delivers a crate of raw materials (raw JSON payload), the intake officer doesn't just stare at it. They instantly cross-reference the crate's contents with the strict `Product` blueprint we built on Day 4. If it clears inspection, the officer instantly unpacks the cargo and assembles it into a live, fully operational machine right on the spot—automatically instantiating a clean Python object. We assign this newly assembled machine a tracking tag (our parameter name, `payload`), giving us direct, type-safe control to inspect individual components (using `payload.name` or `payload.price`) before returning the verified object back to the client as an official intake receipt.

### Day 6: The Postman Order Pad vs. The Transient Memory Waiter
* **What I did:** Orchestrated full-stack boundary integration testing using Postman to verify the unified interplay between our raw JSON payloads, the Pydantic validation shield (`Product`), and our state-changing POST gateway (`/product`).
* **The Logic:** Think of our current engine setup like a waiter taking your order at a restaurant. Postman is you—the customer—reading the menu and sending a raw JSON text order body across the wire. This text acts like a precision-cut key designed to see if it can successfully unlock our combined `@app.post("/product")` and `Product` class door. Our FastAPI backend acts as the waiter. When you hand over the order, the waiter immediately checks it against their pad to ensure it’s valid (Pydantic validation). If an honest customer writes down a price as a string `"20.5"` or an integer `20`, our Pydantic waiter doesn't throw a tantrum; it acts as an intelligent data parser rather than a rigid type-checker, safely performing **data coercion** to transform that input into the exact schema-required float. However, if the key is warped—like omitting a price or sending a text string like `"free"`—the validation engine instantly throws a `422 Unprocessable Content` error, automatically returning a crystal-clear JSON breakdown pinpointing the exact location (`"loc": ["body", "price"]`) and the precise reason (`"msg": "Input should be a valid number"`) for the failure. Once the order clears inspection, the waiter smiles and says, *"Got it! One Chainsaw for $20.0!"* (returning our `200 OK` response). But there is a catch: because we haven't wired up our ledger book (PostgreSQL database) yet, the waiter is just holding this data in their head. The exact millisecond they walk away to serve the next request, that order is completely forgotten.

### Day 7: The Architect’s Blueprints vs. The Site Foreman’s Clipboard (Decoupling Config)
* **What I did:** Implemented decoupled environment-based configurations by introducing a local `.env` variables sheet and binding it to a type-safe Pydantic `BaseSettings` schema in `config.py` to isolate our system secrets from our core application logic.
* **The Logic:** As we prepare to wire up our PostgreSQL database, we cannot hardcode server credentials or ports directly into our codebase. To solve this, we separated our system into two distinct components: **The Site Foreman’s Clipboard (`.env`)** and **The Architect’s Blueprints (`config.py`)**. 
  Our `.env` file contains raw, environment-specific facts (like `DATABASE_PORT=5432` and `DATABASE_USERNAME=postgres`). This file stays strictly local to our workspace. Meanwhile, our `Settings` class inherits from Pydantic's `BaseSettings`, acting as our strict architectural blueprint. When initialized, it automatically goes to the clipboard (`env_file = ".env"`), parses the raw text strings, and validates/coerces them into their correct Python native types (`int`, `str`, `bool`). If someone accidentally configures a port as `"fifty-four"` instead of an integer `5432`, our Pydantic settings module will raise a validation crash during boot. This ensures that our engine cannot even start up with corrupted or missing environmental configuration parameters, giving us an immutable, single source of truth (`settings`) across our entire backend.

### Day 8: The HDMI Cable Handshake & The Standard Playdough Mold (Database Connection)
* **What I did:** Implemented our core PostgreSQL database connection architecture in `database.py` and scaled our Pydantic `BaseSettings` configurations in `config.py` to securely digest, validate, and inject raw environment variables from our local `.env` sheet.
* **The Logic:** Up until now, our FastAPI backend has been like a waiter holding orders in their temporary head—the moment the request completes, the data is forgotten forever. To immortalize our data, we needed to wire up our PostgreSQL database (which acts like a permanent TV screen displaying our permanent state). First, we gathered all our credentials from `.env` and processed them through our Pydantic `Settings` class to assemble our unified `DATABASE_URL` connection string—this acts like holding all 5 colored pins of our HDMI cable in our hand. Next, we initialized `create_engine`—which physically installs the multi-colored HDMI input ports on the back of our TV so it can receive high-speed data signals. We then created our `SessionLocal` factory, which is the pre-configured connection cable itself. By binding it directly to the engine (`bind=engine`) with safe transaction controls (`autocommit=False, autoflush=False`), we've plugged the configured wire directly into the TV's port; whenever a user makes an API request, we grab a single temporary wire, let the electrical current flow to complete the transaction, and unplug it immediately to keep our system clean. Finally, we declared our `Base = declarative_base()`. If we want to shape raw playdough (data) into stars, hearts, or circles, `Base` is our standard cookie-cutter playdough template. Every database table we build next (like a `Product` or `User`) will "snap onto" this `Base` template, acting as the universal schema translation layer so PostgreSQL knows exactly how to read and build physical, permanent tables in the database.
### Day 9: The Blueprint Blueprint vs. The Cement Foundation (SQLAlchemy Models)
* **What I did:** Created the foundational relational database model (Product) inside models.py using SQLAlchemy Declarative Base mapping to define our permanent PostgreSQL database schema constraints.
* **The Logic:** On Day 4, we built a Pydantic Product model, which acted as our automated store turnstile checking customers bags *as they walk through the door*. Today, we built an SQLAlchemy Product model inside models.py, which is something completely different: it is the **blueprinted layout for the heavy cement storage foundation (__tablename__ = "products") poured directly inside our PostgreSQL warehouse floor**. 

During this build, I made five critical assumptions that completely broke the engine until I learned the underlying rules of relational database mapping:
1. **The Wildcard Import Assumption vs. The Explicit Inventory Ledger:** I initially thought using 'from database import *' was a fast way to grab our tools. It broke because it pollutes our namespace and creates a dark "black box." **The Rule:** *Always Use Explicit Imports*. We imported exactly 'from database import Base' to keep our tracking scannable and modular.
2. **The Native Data Type Assumption vs. The SQL Steel Rebar:** I tried passing raw Python types like 'int' or 'str' directly into 'Column()'. It crashed because PostgreSQL doesn't speak Python; it speaks SQL. **The Rule:** *Separate the Code Layer from the Storage Layer*. We must use explicit uppercase translator objects ('Integer', 'String', 'Float') so SQLAlchemy can translate our Python objects into hard SQL columns.
3. **The Property Assignment vs. The Binary Toggle:** I assumed passing 'primary_key=id' would link the key configuration to the identity of the column. It failed because ORM configuration parameters are strictly true/false toggles. **The Rule:** *Configuration Parameters Are Binary Switches*. We set 'primary_key=True' to flip the switch on, while the column's actual name is determined cleanly by the variable on the left side ('id = Column(...)').
4. **The Business Rules vs. The Flexible Warehouse Floor:** I assumed that because a product description is highly important to a business, it should be blocked from being empty at the database layer using 'nullable=False'. This broke flexibility because database barriers are unyielding; if a user tries to save a quick product draft without a description, the database crashes the whole transaction. **The Rule:** *Enforce Business Logic at the Application Layer, Not the Database Layer*. We set 'nullable=True' on the description column to keep the warehouse floor accommodating, leaving strict validation to our Pydantic sentries upstairs.
5. **The Raw Numeric Default vs. The Raw SQL Scripting String:** I passed a raw Python integer '0' into 'server_default'. It broke because 'server_default' completely bypasses Python and directly instructs the database engine what to execute during migrations. **The Rule:** *Server Defaults Must Be String Literals*. We wrapped it in quotes ('server_default="0"') because declarative variables must be explicit string patterns that match exact SQL defaults.

### Day 10: Commissioning the Construction Crew (App-to-DB Ignition)

Right now, PostgreSQL has no idea that our `Product` table blueprint from Day 9 even exists. It's a drawing sitting on a desk. Today, we wired our central application hub (`main.py`) directly to the raw database engine at startup to bridge this gap. 


### Day 11: Request Lifecycle Session Dependency & The Automated Hatch
The Vault Key & The Automated Hatch
Think of our database connection pool as a stack of specialized vault keys, and every incoming HTTP request as a customer walking up to a bank teller window. The bank cannot hand out permanent keys to every visitor without running out and leaving the locks vulnerable, nor can it rely on manual tracking that constantly risks leaving vault doors wide open.

To solve this, we built an automated hatch mechanism (get_db) that acts as a secure intermediary. When a request's turn arrives, the hatch slides out a single, fresh, isolated session key for the duration of that specific transaction. The application uses it inside a protected window to handle its business, and the absolute moment the interaction ends—whether it succeeds or crashes halfway through—a mechanical trapdoor (finally) instantly grabs the connection back and drops it safely into the return bin (db.close()).


## Day 12: The Bank Teller Database Communication Layer (@app.post("/product"))
Today, we built the core database communication pipeline for incoming product creations. If the FastAPI route is the bank teller window, our endpoint is the exact moment a customer walks up with a validated deposit slip, gets their data translated, and permanently logs it into the vault.

Here is how the pipeline operates under the hood:

The Deposit Slip & Translator (.model_dump() & **): The incoming request payload arrives as a rigid, validated Pydantic object—much like a strict, pre-screened deposit form. We call .model_dump() to convert that object into a standard Python dictionary (e.g., {"title": "Laptop", "price": 1000}). From there, double-star unpacking (**) acts as an automated clerk, taking every key-value pair from that dictionary and feeding them directly into our models.Product blueprint all at once, eliminating manual field mapping.

The Temporary Holding Zone (db.add()): Once the SQLAlchemy model instance is created, db.add(new_product) places the row into temporary memory (the session staging area). It's sitting on the counter, ready to be finalized, but not yet written to disk.

The Permanent Seal (db.commit()): Running db.commit() is the official stamp of approval. It permanently writes the row into our PostgreSQL database table, locking the transaction into history.

The Final Identity Stamp (db.refresh()): Finally, db.refresh(new_product) updates our Python instance with the database's freshly generated auto-incrementing ID and default fields, ensuring we hand back a fully synced object to the client.


## Day 13: Building the Product Retrieval GET Route (The Filing Room & Clerk Workflow)
Today, we built our very first HTTP GET route at /products to pull every single item stored in our inventory database. To truly understand how FastAPI, SQLAlchemy, and PostgreSQL hand off data under the hood, I broke it down using a real-world physical analogy: The Filing Room and the Counter Clerk.

The Client Request (The Customer at the Counter): A client sends an HTTP GET request, walking up to the service counter and handing the clerk a slip saying: "Give me all the records in the products file."

Step 1: Opening the Session (The Clerk Opens the Room): Before any work happens, our backend dependency injection opens up an isolated database session. This is like the clerk unlocking the door to the filing room and stepping inside.

Step 2: Executing the Query (Pulling the Records): We run db.query(models.Product).all(). This translates to the clerk walking directly up to the products filing cabinet specifically dedicated to our inventory items, pulling the files, and reading through the contents.

Step 3: Packaging the Results (Organizing the Envelope): The raw database rows are gathered, copied, and organized neatly. The clerk places them into an envelope right on her desk, ready to be serialized.

Step 4: Returning the Response (Handing Over the Envelope): Finally, FastAPI converts those objects into a structured JSON response and slides the envelope back across the counter to the client.

## Day 14  Development Diary Entry

* **Concept:** Fetching a Specific Product via Path Parameters (`GET /products/{id}`)
* **The Analogy:** The database is a massive warehouse filled with thousands of metal filing cabinets. Previously, querying all products was like asking the warehouse worker to roll out an entire cabinet. Today, adding `GET /products/{id}` is like walking up to a specific locker, sliding in a key with the exact product ID number on it, and pulling out only that single file card.


## Day 15: Building the Product Update Pipeline (PUT /products/{product_id})
The Mental Model (The Warehouse Supplier Slip):
Building an update route isn't just overwriting data blindly; it's like a supplier walking up with an official update slip. You don't just toss it onto a random desk. First, you walk over to the filing cabinet and pull the exact folder using the product's ID. If the folder doesn't exist, you stop right there and hand back a 404 Not Found.

Once you have the right folder, Pydantic acts as the strict intake clerk checking the slip to make sure the ink and numbers are valid. After validation, you take a pen and apply the changes directly to the card inside the folder. Finally, you lock the cabinet by executing a database commit(), permanently sealing the transaction in the daily logbook so everyone in the warehouse sees the updated reality.

### Day 16: Product Deletion Route
- **Mental Model:** Walking over to the physical filing cabinet drawer, checking if the target product folder actually exists before trying to rip it out, and raising an immediate flag if it's missing. If it's there, we shred the record right out of the PostgreSQL database and commit the change.
- **Code Implemented:** Added the `DELETE /products/{product_id}` endpoint using FastAPI path parameters and SQLAlchemy session management (`db.get` lookup, existence validation with a 404 HTTP exception, `db.delete()`, and final `db.commit()`).


## Day 17: The Warehouse Clerk & The Catalog Slice

Trying to fetch a wholesale catalog of 10,000 items all at once is like having a delivery driver dump 10,000 binders straight onto your desk until the legs snap under the weight. Today, we built the query parameter filter and pagination logic in main.py so we don't crash the server. Now, we walk into the warehouse, hand instructions to the clerk—specifying how many pages to skip, setting a strict limit of 10 items per page so the desk stays clear, and applying an optional search filter to narrow down the exact product collection the user actually wants before a single byte leaves the floor.

### Day 18: Building the Dynamic Query Sorting Mechanism

* **The Problem:** Clients can't just stare at a static dump of 1,000+ product folders on a single shelf. They need the data structured exactly how they want it—whether that's sorting products from lowest to highest price or pulling the newest arrivals to the top.
* **The Analogy:** Imagine walking into a massive warehouse with thousands of product folders lined up on a shelf. Without sorting, you're just grabbing whatever files happen to be closest to the door. Adding query parameters for sorting is like handing the warehouse clerk an extra instruction slip: *"Keep the folders grouped, but arrange this specific batch by price or creation date before handing them over."*
* **The Implementation:** We introduced dynamic sorting parameters (`sortBy` and `order`) into our `/products` endpoint using SQLAlchemy's `getattr` to safely map request strings to database columns, paired with conditional `asc()` and `desc()` execution clauses right before hitting `.offset().limit().all()`.


## Day 19: Using HTTP Patch
Today, we built the partial update engine using HTTP PATCH, moving away from the brute-force replacement model of PUT.If you use PUT, it is like walking into the warehouse archives and shredding an entire product sheet just because a single price tag changed. If you accidentally forget to copy over the description or stock count during that rewrite, the whole record becomes corrupted or invalid.PATCH solves this cleanly. It works like this: pick up a sticky note $\rightarrow$ write down the changed field value on the note $\rightarrow$ walk up to the filing cabinet drawer $\rightarrow$ find the specific item's folder $\rightarrow$ open it $\rightarrow$ apply the sticky note right over the old value.In code, model_dump(exclude_unset=True) isolates exactly what fields the client cared to touch, ignoring everything else. We pull the existing row from PostgreSQL, iterate through the delta map using setattr(), commit the transaction, and refresh. Only the changed attributes get written to disk, keeping our database state atomic and safe.


## Day 20: Implementing Category-to-Product Relationships & Modular Routing
Mental Model: A grocery store without categories is just a giant pile of inventory on the floor where shoppers take forever to find anything. To fix this, we built aisles and shelves. A single category (aisle) can hold multiple products, but an individual product links directly back to its specific category via an aisle stamp (Foreign Key).

Implementation Details:

Created a dedicated categories.py router module implementing RESTful endpoints (POST /categories/ and GET /categories/) with strict uniqueness validation on category names.

Updated models.py to define the Category entity with an explicit primary key and a SQLAlchemy relationship back-populating to the Product model.

Altered the Product model to include a mandatory category_id Foreign Key constraint referencing categories.id, turning isolated product records into a properly structured relational schema.

Integrated the new category router cleanly inside main.py using FastAPI's modular include_router pattern.



### Day 21: Relational Constraints, Category Filtering, and Foreign Key Joins
**The Analogy:** Imagine a massive supermarket where every single product is placed on a specific shelf inside a designated aisle (the Category). When a customer or a stock clerk wants to find all items belonging to a particular department, they don't wander aimlessly through the entire store—they walk directly to that specific aisle and look at the shelves inside it. The foreign key acts like the permanent aisle number printed on the back of each product box, ensuring that every item is securely mapped to its correct home location and can never be misplaced.

Today, we hardened the database layer by enforcing strict relational constraints between products and categories in PostgreSQL, moving away from isolated tables to a cohesive, interconnected schema. Using SQLAlchemy relationships and foreign keys, we built optimized query filters that fetch joined entities across tables instantly, avoiding N+1 performance bottlenecks and maintaining rigid data integrity at the storage level.


## Day 22
Retail Warehouse Directory Verification: Before placing a new shipment of shoes or modifying an existing inventory record on a shelf, we first consult the central warehouse directory board. If a client attempts to assign a product to a non-existent shelf (category ID), we halt the process instantly and reject the payload rather than wandering around looking for a ghost shelf.

## DAY 23: The Supermarket Aisle 
Think of fetching related category data like walking into a supermarket aisle to pick up a product off the shelf. Instead of just grabbing the item and having to wander back to the help desk later just to figure out what section or aisle you're standing in, the product shelf already has a clean sticker slapped right on it with all the aisle details, name, and info built-in. By using SQLAlchemy's joinedload, PostgreSQL hands us the product and its category info in one single efficient trip, completely avoiding missing attribute errors or extra trips back to the database.