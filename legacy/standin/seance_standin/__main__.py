"""Run the stand-in TN3270 server.

  python -m seance_standin

Environment:
  STANDIN_HOST   bind address (default 0.0.0.0)
  STANDIN_PORT   TN3270 port (default 3271)
  HERCULES_CONSOLE  Hercules HTTP console for the COBOL calls (default
                    http://localhost:8038)
  MVS_USER / MVS_PASSWORD  batch credentials for the SEANCSVC jobs
"""
from __future__ import annotations

import os
import time

from .cobol_client import CobolClient
from .server import serve


def main() -> None:
    host = os.environ.get("STANDIN_HOST", "0.0.0.0")
    port = int(os.environ.get("STANDIN_PORT", "3271"))
    server = serve(host=host, port=port, cobol=CobolClient())
    print(f"Seance Insurance stand-in listening on {host}:{port} "
          f"(business logic: real COBOL SEANCSVC on TK4-)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
