from fastapi import FastAPI

from app.db import Base, engine
from app import models


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
