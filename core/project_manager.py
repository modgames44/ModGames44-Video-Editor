import json
from pathlib import Path


def empty_project():
    return {'version': 1, 'media': [], 'clips': [], 'fps': 30}


def save_project(path, data):
    target = Path(path)
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)


def load_project(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('media'), list) or not isinstance(data.get('clips'), list):
        raise ValueError('Formato de proyecto incompatible')
    return data
