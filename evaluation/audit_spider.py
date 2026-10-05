"""Audit Spider evaluation failures without modifying gold SQL."""

import json
import re
from pathlib import Path

from agent.executor import execute_query


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "evaluation" / "results"
SPIDER_DB_DIR = ROOT / "data" / "spider" / "database"


def latest_spider_results():
    files = sorted(RESULTS_DIR.glob("spider_results_*.json"))

    if not files:
        raise SystemExit(
            "No spider_results_*.json found. Run the Spider evaluation first."
        )

    return files[-1]


def db_path(db_id):
    return SPIDER_DB_DIR / db_id / f"{db_id}.sqlite"


def normalize_quotes(sql):
    return re.sub(r'"([^"]*)"', r"'\1'", sql)


def check_gold_trim_sensitive(gold_sql: str, db: Path) -> dict:
    """Does wrapping string equality comparisons in TRIM() change the result?

    Checks equality comparisons anywhere in the SQL, including WHERE and JOIN
    conditions. This helps detect whitespace-padded values in benchmark data.
    """
    base = execute_query(gold_sql, db)

    trimmed_sql = re.sub(
        r"(\b\w+(?:\.\w+)?)\s*=\s*'([^']*)'",
        r"TRIM(\1) = TRIM('\2')",
        gold_sql,
        flags=re.IGNORECASE,
    )

    # Also handle column-to-column equality comparisons, commonly found
    # in JOIN conditions.
    trimmed_sql = re.sub(
        r"(\b\w+(?:\.\w+)?)\s*=\s*(\b\w+(?:\.\w+)?)",
        r"TRIM(\1) = TRIM(\2)",
        trimmed_sql,
        flags=re.IGNORECASE,
    )

    trimmed = execute_query(trimmed_sql, db)

    return {
        "gold_rows": base.row_count if base.ok else None,
        "trimmed_rows": trimmed.row_count if trimmed.ok else None,
        "trim_changes_result": (
            base.ok
            and trimmed.ok
            and base.row_count != trimmed.row_count
        ),
    }

def check_gold_case_sensitive(gold_sql, db):
    base = execute_query(gold_sql, db)

    ci_sql = re.sub(
        r"(\b\w+(?:\.\w+)?)\s*=\s*'([^']*)'",
        r"LOWER(\1) = LOWER('\2')",
        gold_sql,
    )

    ci = execute_query(ci_sql, db)

    return {
        "case_insensitive_changes_result": (
            base.ok
            and ci.ok
            and base.row_count != ci.row_count
        ),
    }


def check_gold_has_duplicates(gold_sql, db):
    result = execute_query(gold_sql, db)

    if not result.ok or result.df is None or result.df.empty:
        return {
            "has_duplicate_rows": False,
            "duplicate_count": 0,
        }

    duplicates = result.df.duplicated().sum()

    return {
        "has_duplicate_rows": bool(duplicates),
        "duplicate_count": int(duplicates),
    }


def classify(record):
    db = db_path(record["db_id"])
    gold_sql = normalize_quotes(record["gold_sql"])

    gold_result = execute_query(gold_sql, db)

    findings = {
        "gold_executes": gold_result.ok,
        "gold_row_count": (
            gold_result.row_count
            if gold_result.ok
            else None
        ),
    }

    if not gold_result.ok:
        return {
            **findings,
            "classification": "benchmark_defect",
            "reason": (
                f"Gold SQL fails to execute: "
                f"{gold_result.error}"
            ),
        }

    trim_check = check_gold_trim_sensitive(
        gold_sql,
        db,
    )

    findings.update(trim_check)

    if trim_check["trim_changes_result"]:
        return {
            **findings,
            "classification": "possible_data_format_issue",
            "reason": (
                "Gold result changes when string comparisons "
                "are TRIM()'d."
            ),
        }

    case_check = check_gold_case_sensitive(
        gold_sql,
        db,
    )

    findings.update(case_check)

    if case_check["case_insensitive_changes_result"]:
        return {
            **findings,
            "classification": "possible_case_issue",
            "reason": (
                "Gold result changes with case-insensitive "
                "matching."
            ),
        }

    duplicate_check = check_gold_has_duplicates(
        gold_sql,
        db,
    )

    findings.update(duplicate_check)

    if duplicate_check["has_duplicate_rows"]:
        return {
            **findings,
            "classification": "possible_duplicate_issue",
            "reason": (
                f"Gold query returns "
                f"{duplicate_check['duplicate_count']} "
                "duplicate row(s)."
            ),
        }

    if gold_result.row_count == 0:
        return {
            **findings,
            "classification": "legitimate_empty",
            "reason": (
                "Gold SQL executes and returns zero rows."
            ),
        }

    return {
        **findings,
        "classification": "needs_manual_review",
        "reason": (
            "No automatic benchmark/data issue was detected. "
            "Compare gold SQL and final SQL manually."
        ),
    }


def main():
    result_file = latest_spider_results()

    data = json.loads(
        result_file.read_text(encoding="utf-8")
    )

    records = [
        r
        for r in data["records"]
        if r["config"] == "self_correction"
        and not r["correct"]
    ]

    print(
        f"Auditing {len(records)} self-correction failures "
        f"from {result_file.name}\n"
    )

    report = []

    for record in records:
        audit = classify(record)

        report.append(
            {
                **record,
                "audit": audit,
            }
        )

        print(
            f"Q{record['id']:>3} "
            f"({record['db_id']}): "
            f"{audit['classification']}"
        )

        print(
            f"      {audit['reason']}"
        )

        print()

    counts = {}

    for record in report:
        category = record["audit"]["classification"]
        counts[category] = counts.get(category, 0) + 1

    print("Summary:")
    print(counts)

    timestamp = result_file.stem.replace(
        "spider_results_",
        "",
    )

    output_file = (
        RESULTS_DIR
        / f"spider_audit_{timestamp}.json"
    )

    output_file.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()