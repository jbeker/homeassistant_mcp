"""Async HTTP client wrapper for the Home Assistant REST API."""

import httpx


class HAClient:
    """Thin async wrapper around httpx for Home Assistant API calls."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get(self, path: str, **kwargs) -> dict | list | str:
        try:
            resp = await self._client.get(path, **kwargs)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            return resp.text
        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}", "detail": exc.response.text}
        except httpx.RequestError as exc:
            return {"error": "request_failed", "detail": str(exc)}

    async def post(self, path: str, json: dict | None = None, **kwargs) -> dict | list | str:
        try:
            resp = await self._client.post(path, json=json, **kwargs)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.json()
            return resp.text
        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}", "detail": exc.response.text}
        except httpx.RequestError as exc:
            return {"error": "request_failed", "detail": str(exc)}

    async def delete(self, path: str, **kwargs) -> dict | str:
        try:
            resp = await self._client.delete(path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}", "detail": exc.response.text}
        except httpx.RequestError as exc:
            return {"error": "request_failed", "detail": str(exc)}

    async def get_raw(self, path: str, **kwargs) -> bytes:
        """Return raw bytes (e.g. camera image)."""
        try:
            resp = await self._client.get(path, **kwargs)
            resp.raise_for_status()
            return resp.content
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise RuntimeError(str(exc)) from exc

    async def close(self) -> None:
        await self._client.aclose()
