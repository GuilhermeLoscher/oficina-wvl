from __future__ import annotations

import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent / "WVL_web"
sys.path.insert(0, str(APP_DIR))

from app import app  # noqa: E402


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
