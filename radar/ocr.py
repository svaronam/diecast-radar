"""OCR de historias con Tesseract (programa externo, sin dependencias de Python).

Raspberry:  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa   (lo hace install.sh)
Windows:    instalador de UB Mannheim (github.com/UB-Mannheim/tesseract/wiki); opcional para probar.
"""
import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

_WIN_PATHS = [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]
_exe = None
_langs = None


def _find():
    global _exe
    if _exe is None:
        _exe = shutil.which("tesseract") or next((p for p in _WIN_PATHS if os.path.exists(p)), "") or ""
        if not _exe:
            log.warning("OCR no disponible (no encuentro tesseract): las historias se juzgarán solo por sus enlaces")
    return _exe


def available() -> bool:
    return bool(_find())


def _languages():
    global _langs
    if _langs is None:
        try:
            out = subprocess.run([_find(), "--list-langs"], capture_output=True, text=True, timeout=20).stdout
            have = set(out.split())
            _langs = "+".join(l for l in ("eng", "spa") if l in have) or "eng"
        except Exception:
            _langs = "eng"
    return _langs


def read_text(image_path: str, timeout: int = 90) -> str:
    """Texto de la imagen ('' si no hay OCR o falla). --psm 11: texto suelto, típico de historias."""
    exe = _find()
    if not exe or not os.path.exists(image_path):
        return ""
    try:
        r = subprocess.run([exe, image_path, "stdout", "-l", _languages(), "--psm", "11"],
                           capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        log.warning("OCR falló en %s: %s", image_path, e)
        return ""
