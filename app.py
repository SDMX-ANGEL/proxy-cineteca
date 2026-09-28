from flask import Flask, request, Response
from flask_cors import CORS
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
import re
import requests

app = Flask(__name__)
CORS(app)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
URI_ATTR = re.compile(r'URI="([^"]*)"', re.I)
EXCLUDED = {
    "content-encoding",
    "transfer-encoding",
    "connection",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "set-cookie",
}


def unwrap_proxy_url(raw):
    current = (raw or "").strip()
    for _ in range(8):
        parsed = urlparse(current)
        path = parsed.path.rstrip("/") or "/"
        inner = None
        if path in ("/proxy", "/api/proxy") or path.endswith("/proxy"):
            inner = (parse_qs(parsed.query).get("url") or [None])[0]
        if not inner:
            match = re.search(r"/(?:api/)?proxy\?url=([^&]+)", current, re.I)
            if match:
                try:
                    inner = unquote(match.group(1))
                except Exception:
                    break
        if not inner or inner == current:
            break
        current = inner
    return current


def is_likely_playlist(content_type, url):
    if re.search(r"mpegurl|m3u8|vnd\.apple\.mpegurl", content_type or "", re.I):
        return True
    path = urlparse(url).path.lower()
    return path.endswith(".m3u8") or path.endswith(".m3u")


def should_proxy_uri(uri):
    lower = (uri or "").strip().lower()
    if not lower:
        return False
    if lower.startswith(("data:", "skd:", "urn:", "#")):
        return False
    return True


def already_proxied(uri):
    return bool(re.search(r"/(?:api/)?proxy\?url=", uri, re.I))


def wrap_uri(uri, base_url, proxy_prefix):
    if not should_proxy_uri(uri) or already_proxied(uri):
        return uri
    absolute = unwrap_proxy_url(urljoin(base_url, uri))
    return proxy_prefix + quote(absolute, safe="")


def rewrite_m3u8(content, base_url, proxy_prefix):
    """Resolve relative HLS URIs against the real CDN URL, then wrap once."""
    out = []
    for line in content.splitlines():
        trimmed = line.strip()
        if not trimmed:
            out.append(line)
            continue
        if trimmed.startswith("#"):
            out.append(
                URI_ATTR.sub(
                    lambda m: 'URI="%s"'
                    % wrap_uri(m.group(1), base_url, proxy_prefix),
                    trimmed,
                )
            )
            continue
        out.append(wrap_uri(trimmed, base_url, proxy_prefix))
    return "\n".join(out) + "\n"


def public_proxy_prefix():
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = request.headers.get("X-Forwarded-Host") or request.host
    return "%s://%s/proxy?url=" % (proto, host)


def upstream_headers(target):
    host = (urlparse(target).hostname or "").lower()
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    if any(part in host for part in ("pluto", "jmp2", "samsung")):
        headers["Referer"] = "https://pluto.tv/"
        headers["Origin"] = "https://pluto.tv"
    else:
        parsed = urlparse(target)
        headers["Referer"] = "%s://%s/" % (parsed.scheme, parsed.netloc)
    rng = request.headers.get("Range")
    if rng:
        headers["Range"] = rng
    return headers


@app.route("/proxy", methods=["GET", "HEAD", "OPTIONS"])
def proxy():
    if request.method == "OPTIONS":
        resp = Response(status=204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = (
            "Range, Origin, Accept, Accept-Language"
        )
        resp.headers["Access-Control-Max-Age"] = "86400"
        return resp

    raw = request.args.get("url")
    if not raw:
        return "Falta la URL", 400

    target = unwrap_proxy_url(raw)
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        return "Solo se permiten URLs http(s)", 400

    try:
        resp = requests.get(
            target,
            headers=upstream_headers(target),
            stream=True,
            timeout=45,
            allow_redirects=True,
        )
    except Exception as exc:
        return str(exc), 502

    final_url = unwrap_proxy_url(resp.url or target)
    content_type = resp.headers.get("Content-Type", "")

    if is_likely_playlist(content_type, final_url):
        text = resp.content.decode("utf-8", errors="replace")
        if text.lstrip().startswith("#EXT"):
            rewritten = rewrite_m3u8(text, final_url, public_proxy_prefix())
            out = Response(
                rewritten,
                status=200,
                content_type="application/vnd.apple.mpegurl",
            )
            out.headers["Access-Control-Allow-Origin"] = "*"
            out.headers["Cache-Control"] = "no-store"
            return out

    headers = []
    for name, value in resp.raw.headers.items():
        if name.lower() not in EXCLUDED:
            headers.append((name, value))
    headers.append(("Access-Control-Allow-Origin", "*"))
    headers.append(
        (
            "Access-Control-Expose-Headers",
            "Content-Length, Content-Range, Accept-Ranges",
        )
    )

    return Response(
        resp.iter_content(chunk_size=65536),
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type"),
        headers=headers,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
