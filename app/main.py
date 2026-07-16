from fastapi import FastAPI
from app.db import Base, engine
from app import models
from app.isir_client import get_last_podnet_id

app = FastAPI()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {"status": "ISIR Monitor running"}

@app.get("/health")
def health():
    return {"database": "configured"}

@app.get("/isir/last-id")
def isir_last_id():

    last_id = get_last_podnet_id()

    return {"last_id": last_id}