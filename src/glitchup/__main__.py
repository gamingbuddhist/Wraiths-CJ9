import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import Type

# import httpx
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from hypercorn.asyncio import serve
from hypercorn.config import Config
from rq.command import send_shutdown_command
from web.filters.builtin.dotted import Dotted  # type: ignore
from web.filters.builtin.ghosting import Ghosting  # type: ignore
from web.filters.builtin.metaldot import MetalDot  # type: ignore
from web.filters.builtin.number import Number  # type: ignore
from web.filters.image_filter import ImageFilter  # type: ignore
from web.models import FilterMetadata  # type: ignore
from web.worker import Worker, redis_conn, redis_queue  # type: ignore

app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=Path(BASE_DIR, "web/static")), name="static")


@app.on_event("startup")
async def setup() -> None:
    """Configure and set a few things on app startup."""
    redis_conn.sadd(
        "filters",
        str(Ghosting.to_dict()),
        str(Dotted.to_dict()),
        str(Number.to_dict()),
        str(MetalDot.to_dict()),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    """Shutdown the web server and connections to database."""
    for worker in Worker.all(queue=redis_queue):
        send_shutdown_command(redis_conn, worker.name)
        worker.close()

    redis_queue.delete()
    redis_conn.close()


@app.get("/")
async def root() -> FileResponse:
    """Return the root page."""
    return FileResponse(f"{BASE_DIR}/web/static/index.html")


@app.get("/filters")
async def get_all_filters() -> JSONResponse:
    """Return all filters."""
    filters = redis_conn.smembers("filters")

    return JSONResponse(
        content={
            "filters": [
                dict(FilterMetadata.parse_raw(f.translate(f.maketrans("'()", '"[]'))))
                for f in filters
            ]
        },
        status_code=200,
    )


@app.get("/filters/filter/{filter_id}")
async def get_filter(filter_id: int) -> Type[ImageFilter]:
    """Get a filter by ID."""
    ...


@app.post("/filters/create/")
async def create_filter(filter_metadata: FilterMetadata) -> Type[ImageFilter]:
    """Create a new filter."""
    filter_cls = type(f"{filter_metadata.name}", (ImageFilter,), {})
    filter_cls.__doc__ = filter_metadata.description
    setattr(filter_cls, "filter_id", filter_metadata.filter_id)

    redis_conn.sadd(
        "filters",
        str(filter_cls.to_dict()),  # type: ignore
    )

    return filter_cls


@app.post("/images/upload")
async def upload_image() -> uuid.UUID:
    """Upload an image to the server."""
    image_id = uuid.uuid4()

    return image_id


@app.websocket("/images/{image_id}/apply/{filter_id}")
async def apply_filter_to_image(ws: WebSocket, image_id: int, filter_id: int) -> None:
    """Apply a filter to an image."""
    await ws.accept()
    # worker = Worker()

    ...


subprocess.run(["redis-server", "--daemonize", "yes"])
asyncio.run(serve(app, Config()))  # type: ignore
