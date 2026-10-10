import json
from pathlib import Path

from backend.config import Settings
from backend.main import create_app

app = create_app(Settings(_env_file=None, inference_mode="mock"))
path = Path("docs/openapi.json")
path.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(path)
