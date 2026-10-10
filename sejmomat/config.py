import os
from pathlib import Path

TERM = 10
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"  # raw PDF/DOCX downloads, not committed
ACTS = DATA / "acts"   # consolidated texts of amended acts (committed)
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

# Sittings this close to the newest one are re-fetched on every run,
# because the Sejm sometimes corrects records after publishing them.
REFRESH_LAST_SITTINGS = 2

# Public base URL ("https://example.org/sejmomat/"), used for canonical
# links and the sitemap. Left empty for local builds.
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/") + "/" if os.environ.get("SITE_URL") else ""
