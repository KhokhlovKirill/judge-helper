import hashlib
import os
from sqlalchemy import create_engine, select
from server import store as S


def fingerprints(url):
    engine = create_engine(url)
    with engine.connect() as db:
        counts = {}
        for table in S.metadata.sorted_tables:
            query = select(table).order_by(*table.primary_key.columns)
            rows = db.execute(query).all()
            counts[table.name] = (
                len(rows),
                hashlib.sha256(repr(rows).encode()).hexdigest(),
            )
    engine.dispose()
    return counts


if __name__ == "__main__":
    original = fingerprints(os.environ["DATABASE_URL"])
    restored = fingerprints(
        os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/judge_restored"
    )
    assert original["events"][0] > 0 and original == restored
    print("Restored all tables successfully", original)
