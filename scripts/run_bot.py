#!/usr/bin/env python3
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from league_telegram_bot.telegram_main import main as run_main

    run_main()


if __name__ == "__main__":
    main()
