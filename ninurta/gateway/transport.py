"""Newline-delimited JSON-RPC transport for the Ninurta TUI gateway.

Mirrors hermes-agent tui_gateway/transport.py semantics:
- one JSON frame per line on stdout (never mixed with logs — those go to stderr)
- requests carry an ``id`` → responses; frames without ``id`` → push events
- the gateway emits a ``gateway.ready`` event once the loop starts

Handlers run inside a ``ThreadPoolExecutor`` so that long-running calls
(e.g. LLM inference in ``session.send``) never block the stdin read loop.
A ``threading.Lock`` ensures each JSON frame is written atomically to stdout
even when multiple handler threads call ``send_event`` concurrently.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[dict, "JSONRPCTransport"], Any]


class JSONRPCTransport:
    """Reads JSON-RPC frames from stdin, dispatches handlers in a thread pool,
    writes responses/events to stdout.
    """

    def __init__(self, dispatch_map: dict[str, Handler]) -> None:
        self.dispatch_map = dispatch_map
        self._write_lock = threading.Lock()          # stdout line atomicity
        self._pool = ThreadPoolExecutor(max_workers=4)

    # ── Sending ───────────────────────────────────────────────────────────
    def _write(self, obj: dict) -> None:
        """Write one JSON frame to stdout atomically."""
        line = json.dumps(obj) + "\n"
        with self._write_lock:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except BrokenPipeError:
                logger.info("stdout closed — peer gone, stopping.")
                raise SystemExit(0)

    def send_response(self, request_id: Any, result: Any = None, error: Any = None) -> None:
        resp: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            resp["error"] = error
        else:
            resp["result"] = result
        self._write(resp)

    def send_event(self, method: str, params: dict) -> None:
        """Push an async event (SSE-style) to the frontend."""
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    # ── Handler runner (called in worker thread) ──────────────────────────
    def _run_handler(self, handler: Handler, req_id: Any, params: dict) -> None:
        try:
            result = handler(params, self)
            if req_id is not None:
                self.send_response(req_id, result=result)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("error in handler")
            if req_id is not None:
                self.send_response(
                    req_id,
                    error={"code": -32000, "message": str(exc)},
                )

    # ── Loop ──────────────────────────────────────────────────────────────
    def run_loop(self) -> None:
        logger.info("gateway ready")
        self.send_event("gateway.ready", {"status": "ready"})

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("dropping non-JSON frame: %r", line[:120])
                continue

            method_name = req.get("method")
            req_id = req.get("id")
            params = req.get("params") or {}

            handler = self.dispatch_map.get(method_name)
            if handler is None:
                if req_id is not None:
                    self.send_response(
                        req_id,
                        error={"code": -32601, "message": f"method not found: {method_name}"},
                    )
                continue

            # Submit handler to thread pool — read loop stays unblocked
            self._pool.submit(self._run_handler, handler, req_id, params)

        self._pool.shutdown(wait=True)
