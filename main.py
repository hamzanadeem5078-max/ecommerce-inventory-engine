from fastapi import FastAPI 
app = FastAPI() # making the department + door

@app.get("/") # front desk of the hotel lobby where rec is
async def root(): # welcome inside function
    return {"message": "Welcome to the Flash Sale Engine!"}