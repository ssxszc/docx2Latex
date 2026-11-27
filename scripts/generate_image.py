#!/usr/bin/env python3
"""Generate one image through a user-selected OpenAI-compatible Images API."""

import argparse
import base64
import binascii
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE = 64 * 1024 * 1024
TIMEOUT = 180


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_url(url):
    parts = urlsplit(url)
    if not parts.hostname or parts.username is not None or parts.password is not None or parts.fragment:
        raise ValueError("Use a URL without embedded credentials or a fragment.")
    return parts


def generation_endpoint(url):
    parts = parse_url(url)
    if parts.query:
        raise ValueError("Use a generation endpoint without a query string.")
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("The generation endpoint needs HTTPS or loopback HTTP.")
    url = url.rstrip("/")
    return url if parts.path.rstrip("/").endswith("/images/generations") else url + "/images/generations"


def request_bytes(request, action):
    try:
        with build_opener(NoRedirect()).open(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_RESPONSE + 1)
    except HTTPError as exc:
        raise ValueError(f"{action} returned HTTP {exc.code}.") from None
    except (URLError, OSError):
        raise ValueError(f"{action} could not be reached or timed out.") from None
    if len(data) > MAX_RESPONSE:
        raise ValueError(f"{action} response exceeds the size limit.")
    return data


def download_image(url):
    parts = parse_url(url)
    if parts.scheme != "https":
        raise ValueError("A returned image URL must use HTTPS.")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("The returned image host could not be resolved.") from None
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise ValueError("A returned image URL must resolve to a public address.")
    return request_bytes(Request(url, headers={"Accept": "image/*"}), "Image download")


def image_bytes(item):
    if isinstance(item.get("b64_json"), str):
        try:
            return base64.b64decode(item["b64_json"], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("The provider returned invalid base64 image data.") from None
    if isinstance(item.get("url"), str):
        return download_image(item["url"])
    raise ValueError("The provider returned neither b64_json nor an image URL.")


def validate_format(data, suffix):
    formats = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if not formats.get(suffix.lower(), False):
        raise ValueError("The image format does not match --output. Use an appropriate PNG, JPEG or WebP filename.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="API base URL (e.g. https://host/v1) or full generation endpoint.")
    parser.add_argument("--model", required=True, help="Provider model ID.")
    parser.add_argument("--key-env", required=True, help="Environment variable containing the API bearer token.")
    parser.add_argument("--prompt-file", required=True, type=Path, help="UTF-8 file containing only the exact outgoing prompt.")
    parser.add_argument("--output", required=True, type=Path, help="Expected PNG, JPEG or WebP output path.")
    parser.add_argument("--size", help="Optional image size supported by the provider.")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.key_env):
        raise ValueError("--key-env takes an environment variable name.")
    key = os.environ.get(args.key_env)
    if not key or "\r" in key or "\n" in key:
        raise ValueError("Configure a valid API key in the selected environment variable.")
    if args.output.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("--output must end in .png, .jpg, .jpeg or .webp.")
    if args.output.exists():
        raise ValueError("The output already exists. Choose a new filename for this request.")
    prompt = args.prompt_file.read_bytes().decode("utf-8")
    if not prompt.strip() or not args.model.strip():
        raise ValueError("The prompt and model must both be nonempty.")
    payload = {"model": args.model, "prompt": prompt, "n": 1}
    if args.size:
        payload["size"] = args.size
    request = Request(
        generation_endpoint(args.endpoint), data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    raw_response = request_bytes(request, "Image generation")
    try:
        response = json.loads(raw_response)
        item = response["data"][0]
        if not isinstance(item, dict):
            raise TypeError
    except (UnicodeError, ValueError, TypeError, KeyError, IndexError):
        raise ValueError("The provider did not return a valid images response.") from None
    data = image_bytes(item)
    validate_format(data, args.output.suffix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as out:
        out.write(data)
    reported_model = response.get("model")
    print(json.dumps({
        "backend": "openai-compatible",
        "requested_model": args.model,
        "reported_model": reported_model if isinstance(reported_model, str) else None,
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
