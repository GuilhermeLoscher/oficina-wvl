from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent / "WVL_web"
sys.path.insert(0, str(APP_DIR))

spec = importlib.util.spec_from_file_location("wvl_web_app", APP_DIR / "app.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Nao foi possivel carregar WVL_web/app.py")

module = importlib.util.module_from_spec(spec)
sys.modules["wvl_web_app"] = module
spec.loader.exec_module(module)

app = module.app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
