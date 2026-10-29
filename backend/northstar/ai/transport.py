"""Bounded provider HTTP transport. Secrets/content travel over stdin, never CLI arguments."""

import json
import subprocess
import sys
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Provider redirects are prohibited")


def post_json(url, payload, timeout, api_key=None):
    # A process deadline also bounds slow/trickling responses, DNS and response headers.
    result = subprocess.run(
        [sys.executable, "-m", "northstar.ai.transport"],
        input=json.dumps({"url": url, "payload": payload, "timeout": timeout, "key": api_key}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if result.returncode != 0 or len(result.stdout) > 128 * 1024:
        raise ValueError("Provider transport failed")
    return json.loads(result.stdout)


def main():
    try:
        message = json.load(sys.stdin)
        headers = {"Content-Type": "application/json"}
        if message["key"]:
            headers["Authorization"] = "Bearer " + message["key"]
        request = Request(
            message["url"],
            data=json.dumps(message["payload"]).encode(),
            headers=headers,
            method="POST",
        )
        # A local server must not be silently reached via an external environment proxy.
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=message["timeout"]
        ) as response:
            body = response.read(128 * 1024 + 1)
        if len(body) > 128 * 1024:
            raise ValueError("Response exceeds limit")
        print(json.dumps(json.loads(body)))
    except Exception:
        # Do not expose exceptions, keys, URLs or document passages to process logs.
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
