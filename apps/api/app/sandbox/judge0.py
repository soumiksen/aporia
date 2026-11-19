import asyncio
import base64

import httpx

from app.sandbox.base import RunResult, SandboxError

# Judge0 status ids: 3 accepted, 5 time limit exceeded, 6 compile error, 7-12 runtime errors,
# 13 internal error, 14 exec format error.
STATUS_TLE = 5
STATUS_INTERNAL = 13
STATUS_EXEC_FORMAT = 14


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def unb64(text: str | None) -> str:
    return base64.b64decode(text).decode(errors="replace") if text else ""


class Judge0Runner:
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        language_prefix: str = "Python (3",
        http_timeout_s: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=http_timeout_s)
        self._language_prefix = language_prefix
        self._language_id: int | None = None
        self._lock = asyncio.Lock()

    async def language_id(self) -> int:
        """Resolves the Python 3 language id once via GET /languages (ids are never hardcoded)."""
        async with self._lock:
            if self._language_id is not None:
                return self._language_id
            try:
                res = await self._client.get(f"{self._base_url}/languages")
                res.raise_for_status()
                languages = res.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SandboxError(f"cannot list Judge0 languages: {exc}") from exc
            matches = [
                lang["id"]
                for lang in languages
                if str(lang.get("name", "")).startswith(self._language_prefix)
            ]
            if not matches:
                raise SandboxError("Judge0 has no Python 3 language")
            chosen: int = max(matches)  # newest Python 3 build
            self._language_id = chosen
            return chosen

    async def run(
        self, source: str, stdin: str, time_limit_s: float = 5.0, memory_mb: int = 256
    ) -> RunResult:
        language_id = await self.language_id()
        payload = {
            "source_code": b64(source),
            "language_id": language_id,
            "stdin": b64(stdin),
            "cpu_time_limit": time_limit_s,
            "wall_time_limit": time_limit_s * 2,
            "memory_limit": memory_mb * 1024,  # Judge0 expects kilobytes
            "enable_network": False,
        }
        try:
            res = await self._client.post(
                f"{self._base_url}/submissions",
                params={"base64_encoded": "true", "wait": "true"},
                json=payload,
            )
            res.raise_for_status()
            body = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SandboxError(f"Judge0 request failed: {exc}") from exc

        status_id = int(body.get("status", {}).get("id", 0))
        if status_id in (STATUS_INTERNAL, STATUS_EXEC_FORMAT):
            description = body.get("status", {}).get("description", "internal error")
            raise SandboxError(f"Judge0 {description}")
        stderr = unb64(body.get("stderr"))
        if status_id == 6:  # compile error: surface the compiler output as stderr
            stderr = unb64(body.get("compile_output")) or stderr
        exit_code = body.get("exit_code")
        return RunResult(
            stdout=unb64(body.get("stdout")),
            stderr=stderr,
            exit_code=int(exit_code) if exit_code is not None else (0 if status_id == 3 else 1),
            timed_out=status_id == STATUS_TLE,
            time_ms=float(body.get("time") or 0) * 1000,
        )
