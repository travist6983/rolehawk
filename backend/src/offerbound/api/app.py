"""FastAPI application. Routes stay thin: validate input, call a service, return its result."""

from fastapi import FastAPI

from offerbound import __version__
from offerbound.services import health

app = FastAPI(title="Offerbound AI", version=__version__)


@app.get("/api/health")
def get_health() -> dict[str, str]:
    return health.status()
