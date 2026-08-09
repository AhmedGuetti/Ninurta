"""Bootstrap entry point for the Ninurta TUI gateway.

Spawned by the Node frontend via::

    python -m ninurta.gateway.entry

Stdout carries newline-delimited JSON-RPC only; all logs go to stderr so
background tracebacks never corrupt the terminal UI.
"""

from __future__ import annotations

import logging
import sys

from ninurta.gateway.methods import get_dispatch_map
from ninurta.gateway.transport import JSONRPCTransport


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("ninurta.gateway")
    logger.info("starting ninurta gateway")

    transport = JSONRPCTransport(get_dispatch_map())
    try:
        transport.run_loop()
    except KeyboardInterrupt:
        logger.info("gateway stopped")
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — crash log to stderr, never stdout
        logger.exception("gateway crashed")


if __name__ == "__main__":
    main()
