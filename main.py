from fastapi import FastAPI
from routes.home import router as home_router

app = FastAPI()

app.include_router(home_router)
