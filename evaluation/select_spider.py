import json
import random
from pathlib import Path

INPUT = Path("data/spider/dev.json")
OUTPUT = Path("evaluation/questions_spider.json")

random.seed(42)

dev = json.loads(INPUT.read_text(encoding="utf-8"))

by_db = {}

for row in dev:
    by_db.setdefault(row["db_id"], []).append(row)

# Choose 10 different databases
db_ids = random.sample(list(by_db.keys()), 10)

chosen = []

for db_id in db_ids:
    rows = by_db[db_id]

    # Up to 4 questions from each database
    chosen.extend(random.sample(rows, min(4, len(rows))))

OUTPUT.write_text(
    json.dumps(chosen, indent=2),
    encoding="utf-8"
)

print(
    f"Selected {len(chosen)} questions "
    f"across {len(set(row['db_id'] for row in chosen))} databases"
)