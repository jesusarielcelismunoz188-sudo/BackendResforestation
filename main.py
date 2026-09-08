from fastapi import FastAPI

app = FastAPI() 
@app.get("/")
async def read_root():
    return("msg" "Hola <3")