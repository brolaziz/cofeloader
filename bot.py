"""CofeSave entry point: python bot.py."""

import asyncio
import sys

from cofesave.app import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
