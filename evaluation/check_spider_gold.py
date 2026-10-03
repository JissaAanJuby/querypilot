import json
from pathlib import Path

from agent.executor import execute_query

QUESTIONS = Path("evaluation/questions_spider.json")

rows = json.loads(QUESTIONS.read_text(encoding="utf-8"))

broken = 0

for i, row in enumerate(rows, start=1):
    db_id = row["db_id"]

    db_path = (
        Path("data")
        / "spider"
        / "database"
        / db_id
        / f"{db_id}.sqlite"
    )

    result = execute_query(row["query"], str(db_path))

    if not result.ok:
        broken += 1

        print(
            f"BROKEN Q{i} | {db_id} | "
            f"{row['question']} | {result.error}"
        )

print()
print(f"{broken} broken out of {len(rows)}")