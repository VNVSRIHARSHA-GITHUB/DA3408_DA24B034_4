"""
Webhook receiver for Alertmanager: prints one line per firing/resolved alert.
Started by monitoring/docker-compose.yml on port 5001 (standard library only).
"""

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 5001

COLORS = {"firing": "\033[91m", "resolved": "\033[92m"}  # red / green
RESET = "\033[0m"


class AlertHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        now = datetime.now().strftime("%H:%M:%S")
        for alert in payload.get("alerts", []):
            status = alert.get("status", "unknown")
            labels = alert.get("labels", {})
            summary = alert.get("annotations", {}).get("summary", "")
            color = COLORS.get(status, "")
            print(
                f"{now}  {color}{status.upper():8s}{RESET}  "
                f"{labels.get('alertname', '?'):24s}  "
                f"severity={labels.get('severity', '-'):8s}  {summary}",
                flush=True,
            )

        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # silence the default access log


if __name__ == "__main__":
    print(f"Alert receiver listening on http://0.0.0.0:{PORT}/alert", flush=True)
    HTTPServer(("0.0.0.0", PORT), AlertHandler).serve_forever()
