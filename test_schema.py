import json
from backend.schemas import IntentResult

print(json.dumps(IntentResult.model_json_schema(), indent=2))
