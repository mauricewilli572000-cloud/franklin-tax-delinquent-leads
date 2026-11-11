"""Find and download the newest Franklin County Auditor monthly data drop."""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
import zipfile
from pathlib import Path

import config

log = logging.getLogger(__name__)

try:  # browser-like TLS fingerprint; the Auditor's main site blocks plain clients
    from curl_cffi import requests as _http
    _SESSION = _http.Session(impersonate="chrome")
except Exception:  # pragma: no cover - fallback when curl_cffi is missing
    import requests as _http
    _SESSION = _http.Session()
    _SESSION.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"


def get(url: str, **kw):
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            r = _SESSION.get(url, timeout=config.HTTP_TIMEOUT, **kw)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def _hrefs(html: str, base: str) -> list[str]:
    return [urllib.parse.urljoin(base, h) for h in re.findall(r'href="([^"]+)"', html, re.I)]


def list_drops() -> list[tuple[str, str]]:
    """[(folder_name, folder_url)] of 'Tax Accounting' drops, newest first."""
    years = sorted({m for m in re.findall(r"/Outside_User_Files/(\d{4})/", get(config.OUTSIDE_FILES).text)},
                   reverse=True)
    drops = []
    for y in years[:2]:
        url = f"{config.OUTSIDE_FILES}{y}/"
        for h in _hrefs(get(url).text, url):
            name = urllib.parse.unquote(h.rstrip("/").rsplit("/", 1)[-1])
            if h.endswith("/") and "Tax Accounting" in name and re.match(r"\d{4}-\d{2}-\d{2}", name):
                drops.append((name, h))
    drops.sort(reverse=True)
    return drops


def fetch_drop_files(raw_dir: Path) -> dict:
    """Download Tab-Delimited.zip from the newest drops until every needed file is found.

    Returns {"files": {name: extracted path}, "drops": {name: folder}, "snapshot": "YYYY-MM-DD",
             "signature": str}.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    found: dict[str, Path] = {}
    source: dict[str, str] = {}
    for name, url in list_drops()[: config.MAX_DROPS_TO_SCAN]:
        missing = [f for f in config.NEEDED_FILES if f not in found]
        if not missing:
            break
        zurl = url + urllib.parse.quote(config.TAB_ZIP_NAME)
        zpath = raw_dir / f"{name[:10]}_{config.TAB_ZIP_NAME}"
        try:
            log.info("Downloading %s", zurl)
            r = get(zurl)
            zpath.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            log.warning("Skipping drop %s: %s", name, e)
            continue
        with zipfile.ZipFile(zpath) as z:
            names = {Path(i.filename).name: i for i in z.infolist()}
            for f in missing:
                if f in names:
                    out = raw_dir / f
                    with z.open(names[f]) as src, out.open("wb") as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)
                    found[f] = out
                    source[f] = name
                    log.info("  %s <- %s", f, name)
        zpath.unlink(missing_ok=True)
    lost = [f for f in config.REQUIRED_FILES if f not in found]
    if lost:
        raise RuntimeError(f"Required files not found in recent drops: {lost}")
    snapshot = source["TaxDetail.txt"][:10]
    signature = "|".join(f"{k}={v}" for k, v in sorted(source.items()))
    return {"files": found, "drops": source, "snapshot": snapshot, "signature": signature}


def fetch_advertised(raw_dir: Path) -> list[tuple[str, Path]]:
    """Real-estate advertised delinquent list(s) -> [(year, path)]. Best effort."""
    try:
        html = get(config.ADVERTISED_PAGE).text
    except Exception as e:  # noqa: BLE001
        log.warning("Advertised list page unavailable: %s", e)
        return []
    out = []
    for h in _hrefs(html, config.ADVERTISED_PAGE):
        fname = h.rsplit("/", 1)[-1].lower()
        # The page's link labels are swapped, so pick by file name: '-re-' = real estate.
        if fname.endswith(".xlsx") and "-re-" in fname and "delinquent" in h.lower():
            m = re.search(r"(20\d{2})", fname)
            path = raw_dir / fname
            try:
                path.write_bytes(get(h).content)
                out.append((m.group(1) if m else "", path))
            except Exception as e:  # noqa: BLE001
                log.warning("Could not download %s: %s", h, e)
    return out
