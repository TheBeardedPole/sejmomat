import os
import re
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
# Google Analytics 4 measurement id ("G-XXXXXXXXXX"), a repository variable passed to the build.
# Unset, nothing about analytics is on the site; set, it loads only after the visitor agrees.
GA_ID = os.environ.get("GA_MEASUREMENT_ID", "").strip()
if not re.fullmatch(r"G-[A-Z0-9]{4,20}", GA_ID):
    GA_ID = ""
