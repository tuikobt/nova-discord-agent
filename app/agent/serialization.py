import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time


def encode(value):
    def fallback(item):
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, (datetime, date, time)):
            return item.isoformat()
        raise TypeError("Unsupported agent result")

    return json.dumps(value, ensure_ascii=False, default=fallback)


def plain(value):
    return json.loads(encode(value))
