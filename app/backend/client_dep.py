from typing import Any, AsyncGenerator

from httpx import AsyncClient


async def get_http_client() -> AsyncGenerator[AsyncClient, Any]:
    async with AsyncClient(timeout=10.0) as client:
        yield client
