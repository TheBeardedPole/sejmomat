import sys

from . import build, fetch

COMMANDS = {"fetch": fetch.run, "build": build.run, "ocr": fetch.ocr_scanned}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: python -m lepszy_sejm {{{'|'.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
