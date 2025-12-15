import json
from pathlib import Path

def json_to_dict(data: str) -> dict:
    return json.loads(data)

def read_file_as_text(path: str) -> str:
    file_path = Path(path)
    contents = file_path.read_text()
    return contents
