from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api import runs, health

app = FastAPI(title="Celesto Sandbox Control Plane")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": "invalid request"},
    )

app.include_router(health.router)
app.include_router(runs.router)

@app.get("/")
def root():
    return {"message": "Celesto Sandbox Agent Control Plane"}
