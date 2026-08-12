from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.database.db import get_client

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/customers")
def list_customers():
    db = get_client()
    result = db.table("customers").select("*").execute()
    return result.data

