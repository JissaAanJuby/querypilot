"""Try each stage without the UI.

python try_agent.py "question" --stage 2|3|4 [--prune] [--no-correct] [--demo-fail]
"""
import argparse
import logging

from dotenv import load_dotenv

DB_PATH = "data/chinook.db"


def make_broken_first_client(real):
    """Returns a deliberately wrong query first, then delegates to the real model."""
    from agent.generator import LLMClient

    class BrokenFirstClient(LLMClient):
        def __init__(self):
            self.calls = 0

        def complete(self, system, prompt):
            self.calls += 1
            if self.calls == 1:
                return '{"sql": "SELECT artist_name FROM artists"}'
            return real.complete(system, prompt)

    return BrokenFirstClient()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--stage", type=int, default=4, choices=[2, 3, 4])
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--no-correct", action="store_true")
    parser.add_argument("--demo-fail", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from agent.generator import generate_sql, get_client
    from agent.schema import extract_schema, format_schema, select_relevant_tables

    schema = extract_schema(DB_PATH)
    tables = select_relevant_tables(args.question, schema) if args.prune else None
    schema_text = format_schema(schema, tables)
    real = get_client()
    print(f"Model: {real.model}")
    print(f"Tables sent to model ({len(tables or schema)}): {tables or 'all'}\n")

    if args.stage == 2:
        print("--- Generated SQL ---")
        print(generate_sql(real, args.question, schema_text))
        return

    if args.stage == 3:
        from agent.executor import execute_query
        from agent.validator import validate_sql

        sql = generate_sql(real, args.question, schema_text)
        print("Generated:", sql)
        check = validate_sql(sql)
        if not check.ok:
            print("BLOCKED by validator:", check.error)
            return
        print("Validated:", check.sql)
        result = execute_query(check.sql, DB_PATH)
        if not result.ok:
            print("EXECUTION ERROR:", result.error)
            return
        print(f"{result.row_count} rows in {result.latency_s:.3f}s")
        print(result.df.head(10).to_string(index=False))
        return

    from agent.corrector import run_agent

    client = make_broken_first_client(real) if args.demo_fail else real
    res = run_agent(
        args.question, client, DB_PATH, schema,
        prune=args.prune, self_correct=not args.no_correct,
    )
    print("\n--- Agent activity ---")
    for a in res.attempts:
        print(f"Attempt {a.number} [{a.status}] {a.reason}")
        print("   ", a.sql)
    print(f"\nSuccess: {res.success} | Empty: {res.empty} | Attempts: {len(res.attempts)} | {res.total_latency_s:.2f}s")
    if res.df is not None:
        print(res.df.head(10).to_string(index=False))
    if res.error:
        print("Error:", res.error)


if __name__ == "__main__":
    main()
