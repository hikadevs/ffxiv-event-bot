import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord

from .bot import create_bot
from .config import load_settings


logger = logging.getLogger(__name__)


def start_health_server() -> ThreadingHTTPServer | None:
    port = int(os.getenv("PORT", "8080"))

    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/health", "/healthz"}:
                self.send_error(404, "Not Found")
                return

            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            logger.info("Health check: %s", format % args)

    server = ThreadingHTTPServer(("0.0.0.0", port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server listening on port %s", port)
    return server


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = load_settings()
    bot = create_bot(settings)
    health_server = start_health_server()

    try:
        bot.run(settings.discord_token)
    except discord.LoginFailure as error:
        raise RuntimeError(
            "Discord rejected DISCORD_TOKEN. Generate a new bot token in the "
            "Discord Developer Portal and update .env."
        ) from error
    finally:
        if health_server is not None:
            health_server.shutdown()
            health_server.server_close()


if __name__ == "__main__":
    main()