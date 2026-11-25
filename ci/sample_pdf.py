from pathlib import Path
from server.formats import protocol


def build():
    names = {"a": "Елена Петрова", "b": "Иван Сидоров"}
    event = {
        "title": "Открытый кубок «Весна»",
        "date": "2026-04-18",
        "venue": "Казань",
        "judges": ["a", "b"],
        "chief": "a",
        "approved_at": "2026-04-18 17:30 МСК",
    }
    rows = [
        {
            "rank": 1,
            "name": "Мария Иванова",
            "club": "Старт",
            "technique": 9.1,
            "artistry": 8.8,
            "total": 8.98,
            "category": 1,
        },
        {
            "rank": 2,
            "name": "Ольга Смирнова",
            "club": "Ритм",
            "technique": 8.7,
            "artistry": 9.0,
            "total": 8.82,
            "category": 1,
        },
    ]
    Path("docs/protocol-sample.pdf").write_bytes(protocol(event, rows, names))


if __name__ == "__main__":
    build()
