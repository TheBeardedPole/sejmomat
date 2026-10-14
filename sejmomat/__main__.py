import sys

from . import build, fetch, speeches

COMMANDS = {"fetch": fetch.run, "build": build.run, "ocr": fetch.ocr_scanned,
            "acts": fetch.fetch_acts, "speeches": speeches.fetch}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: python -m sejmomat {{{'|'.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
