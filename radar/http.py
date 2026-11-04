"""Cliente HTTP con cabeceras de navegador y reintentos.

Si está instalado curl_cffi, imita la huella TLS de Chrome (ayuda con webs
protegidas por Cloudflare/Akamai, p. ej. Mattel Creations). Si no, usa requests.
"""
import logging
import time

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

try:  # opcional
    from curl_cffi import requests as _creq  # type: ignore
except Exception:  # pragma: no cover
    _creq = None

import requests as _requests


class Http:
    def __init__(self, timeout: int = 25):
        self.timeout = timeout
        if _creq is not None:
            self.s = _creq.Session(impersonate="chrome")
            self.backend = "curl_cffi"
        else:
            self.s = _requests.Session()
            self.backend = "requests"
        self.s.headers.update(BASE_HEADERS)

    def get(self, url, *, params=None, headers=None, retries: int = 2):
        last_exc = None
        for attempt in range(retries + 1):
            try:
                r = self.s.get(url, params=params, headers=headers, timeout=self.timeout,
                               allow_redirects=True)
                if r.status_code in (429, 502, 503) and attempt < retries:
                    wait = 10 * (attempt + 1)
                    log.warning("%s -> %s, reintento en %ss", url, r.status_code, wait)
                    time.sleep(wait)
                    continue
                return r
            except Exception as e:  # red caída, timeout...
                last_exc = e
                log.warning("Error pidiendo %s: %s", url, e)
                time.sleep(3 * (attempt + 1))
        raise last_exc

    def json(self, url, **kw):
        r = self.get(url, **kw)
        r.raise_for_status()
        return r.json()

    def text(self, url, **kw):
        r = self.get(url, **kw)
        r.raise_for_status()
        return r.text
