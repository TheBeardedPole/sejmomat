"""Version-stamp the scripts and styles a static page loads.

    python3 -m sejmomat.stamp site/sejmdle

The CDN and browsers keep scripts and styles for a while, so a page could
load an old script for minutes after a deploy. HTML is not cached that way:
referencing "sejmdle.js?v=<hash of the file>" makes a new version load as
soon as the page does. Only local files next to the page are stamped.
"""
import hashlib
import re
import sys
from pathlib import Path

_REF_RE = re.compile(r'(?P<attr>\b(?:src|href)=")(?P<file>[\w.-]+\.(?:js|css))(?:\?v=[0-9a-f]+)?(?P<end>")')


def stamp(folder):
    """Rewrite every *.html in `folder`; returns the stamped references."""
    folder = Path(folder)
    done = []

    def repl(m):
        target = folder / m["file"]
        if not target.is_file():
            return m[0]
        version = hashlib.sha256(target.read_bytes()).hexdigest()[:10]
        done.append(f"{m['file']}?v={version}")
        return f"{m['attr']}{m['file']}?v={version}{m['end']}"

    for page in folder.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        stamped = _REF_RE.sub(repl, text)
        if stamped != text:
            page.write_text(stamped, encoding="utf-8")
    return done


if __name__ == "__main__":
    for ref in stamp(sys.argv[1]):
        print(ref)
