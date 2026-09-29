"""Evaluation harness: execution accuracy, baseline vs self-correction, failure analysis.

Run from project root:
  python -m evaluation.run_eval --check-gold
  python -m evaluation.run_eval --configs baseline,self_correction
All numbers come from real runs. Nothing is hard-coded.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from agent.corrector import run_agent  # noqa: E402
from agent.executor import execute_query  # noqa: E402
from agent.generator import GeminiClient  # noqa: E402
from agent.schema import extract_schema  # noqa: E402

DB_PATH = ROOT / "data" / "chinook.db"
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

CONFIGS = {
    "baseline": {"self_correct": False, "prune": False},
    "self_correction": {"self_correct": True, "prune": False},
    "pruning": {"self_correct": False, "prune": True},
}
LABELS = {"baseline": "Baseline", "self_correction": "Self-Correction", "pruning": "Schema Pruning"}


# ------------------------------------------------------------ comparison --
def _norm_value(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "NULL"
    if isinstance(v, (int, float)):
        return f"{round(float(v), 2):.2f}"
    if isinstance(v, bytes):
        return v.hex()
    s = str(v).strip()
    try:
        return f"{round(float(s), 2):.2f}"  # '2010' (text) == 2010 (int)
    except ValueError:
        return s


def _canonical(df):
    """Order-insensitive rows; values inside a row sorted so column order is ignored."""
    return sorted(
        tuple(sorted(_norm_value(v) for v in row))
        for row in df.itertuples(index=False, name=None)
    )


def results_match(gold_df, pred_df) -> bool:
    """Execution-accuracy comparison. Ignores row order, column order/names, tiny float noise."""
    if gold_df is None or pred_df is None or gold_df.shape != pred_df.shape:
        return False
    return _canonical(gold_df) == _canonical(pred_df)


# ------------------------------------------------------------- evaluation --
def evaluate_config(name, cfg, questions, client, schema, args):
    records = []
    for i, q in enumerate(questions, 1):
        gold = execute_query(q["gold_sql"], DB_PATH)
        if not gold.ok:
            raise SystemExit(f"Gold SQL for question {q['id']} is broken: {gold.error}")

        res = run_agent(
            q["question"], client, str(DB_PATH), schema,
            max_retries=args.max_retries, max_rows=args.max_rows, **cfg,
        )
        if not res.attempts and res.error.startswith("LLM error"):
            raise SystemExit(
                f"Stopped at Q{q['id']}: {res.error}\n"
                "No results saved. Fix the API quota, then rerun."
            )
        correct = res.df is not None and results_match(gold.df, res.df)

        first = res.attempts[0] if res.attempts else None
        first_correct = False
        if first and first.executed_sql and first.status in ("ok", "empty"):
            fr = execute_query(first.executed_sql, DB_PATH)
            first_correct = fr.ok and results_match(gold.df, fr.df)

        rec = {
            "config": name, "id": q["id"], "difficulty": q["difficulty"],
            "question": q["question"], "gold_sql": q["gold_sql"],
            "first_sql": first.sql if first else "",
            "first_status": first.status if first else "llm_error",
            "first_error": first.error if first else res.error,
            "final_sql": res.final_sql, "final_error": res.error,
            "attempts": len(res.attempts),
            "initial_failure": res.initial_failure,
            "answered": res.answered,
            "correct": bool(correct),
            "first_attempt_correct": bool(first_correct),
            "latency_s": round(res.total_latency_s, 3),
            "attempt_log": [
                {"n": a.number, "sql": a.sql, "status": a.status, "error": a.error}
                for a in res.attempts
            ],
        }
        records.append(rec)
        mark = "OK " if correct else "BAD"
        print(f"  [{name}] Q{q['id']:>2} {mark} attempts={rec['attempts']} {rec['latency_s']:.1f}s")
        if i < len(questions):
            time.sleep(args.delay)  # stay under free-tier rate limits
    return records


def summarize(records):
    n = len(records)
    initial = [r for r in records if r["initial_failure"]]
    corrected = [r for r in initial if r["answered"]]
    by_diff = {}
    for r in records:
        d = by_diff.setdefault(r["difficulty"], [0, 0])
        d[0] += r["correct"]
        d[1] += 1
    return {
        "total": n,
        "correct": sum(r["correct"] for r in records),
        "accuracy": 100 * sum(r["correct"] for r in records) / n,
        "first_attempt_accuracy": 100 * sum(r["first_attempt_correct"] for r in records) / n,
        "avg_latency": sum(r["latency_s"] for r in records) / n,
        "failed_queries": sum(not r["answered"] for r in records),
        "initial_failures": len(initial),
        "corrected": len(corrected),
        "remaining_failures": len(initial) - len(corrected),
        "correction_rate": (100 * len(corrected) / len(initial)) if initial else None,
        "avg_attempts": sum(r["attempts"] for r in records) / n,
        "by_difficulty": {k: f"{v[0]}/{v[1]}" for k, v in by_diff.items()},
    }


def write_report(all_records, summaries, path, model):
    lines = [
        "# QueryPilot Evaluation Results", "",
        f"- Date: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Model: {model}",
        f"- Questions: {summaries[next(iter(summaries))]['total']}", "",
        "## Ablation", "",
        "| Configuration | Execution Accuracy | Avg Latency | Failed Queries |",
        "|---|---|---|---|",
    ]
    for name, s in summaries.items():
        lines.append(
            f"| {LABELS[name]} | {s['accuracy']:.1f}% ({s['correct']}/{s['total']}) "
            f"| {s['avg_latency']:.2f} s | {s['failed_queries']} |"
        )
    lines += ["", "## Accuracy by difficulty", "", "| Configuration | " +
              " | ".join(next(iter(summaries.values()))["by_difficulty"].keys()) + " |",
              "|---|" + "---|" * len(next(iter(summaries.values()))["by_difficulty"])]
    for name, s in summaries.items():
        lines.append(f"| {LABELS[name]} | " + " | ".join(s["by_difficulty"].values()) + " |")

    if "self_correction" in summaries:
        s = summaries["self_correction"]
        rate = "n/a" if s["correction_rate"] is None else f"{s['correction_rate']:.1f}%"
        lines += [
            "", "## Failure analysis (self-correction run)", "",
            f"- Total queries: {s['total']}",
            f"- Initial failures (attempt 1 error or empty): {s['initial_failures']}",
            f"- Successfully corrected: {s['corrected']}",
            f"- Remaining failures: {s['remaining_failures']}",
            f"- Correction success rate: {rate}",
            f"- Average attempts per query: {s['avg_attempts']:.2f}",
            f"- Attempt-1 accuracy within this same run: {s['first_attempt_accuracy']:.1f}%", "",
        ]
        recs = [r for r in all_records if r["config"] == "self_correction"]
        lines += ["### Queries that needed correction", ""]
        for r in (x for x in recs if x["initial_failure"]):
            lines += [
                f"**Q{r['id']} ({r['difficulty']}):** {r['question']}",
                f"- First SQL: `{r['first_sql']}`",
                f"- First error: {r['first_error']}",
                f"- Final SQL: `{r['final_sql']}`",
                f"- Attempts: {r['attempts']} | Answered: {r['answered']} | Correct: {r['correct']}", "",
            ]
        lines += ["### Executed successfully but WRONG (semantic errors)", ""]
        wrong = [r for r in recs if r["answered"] and not r["correct"]]
        for r in wrong:
            lines += [f"**Q{r['id']}:** {r['question']}",
                      f"- Predicted: `{r['final_sql']}`", f"- Gold: `{r['gold_sql']}`", ""]
        if not wrong:
            lines.append("None in this run.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default="baseline,self_correction")
    parser.add_argument("--limit", type=int, default=None, help="only first N questions")
    parser.add_argument("--delay", type=float, default=6.0, help="seconds between questions")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--check-gold", action="store_true", help="just run gold SQL and exit")
    parser.add_argument(
    "--questions",
    default=None,
    help="path to a questions JSON file; defaults to questions.json"
    )
    args = parser.parse_args()

    load_dotenv()
    q_path = Path(args.questions) if args.questions else QUESTIONS_PATH
    questions = json.loads(q_path.read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]

    if args.check_gold:
        bad = 0
        for q in questions:
            r = execute_query(q["gold_sql"], DB_PATH)
            note = "" if r.ok and r.row_count < args.max_rows else "  <-- CHECK"
            print(f"Q{q['id']:>2} {'OK ' if r.ok else 'ERR'} rows={r.row_count:<4}{note} {r.error}")
            bad += (not r.ok) or r.row_count >= args.max_rows
        print("\nAll gold queries valid." if not bad else f"\n{bad} problem(s) found.")
        return

    schema = extract_schema(DB_PATH)
    client = GeminiClient()
    names = [c.strip() for c in args.configs.split(",")]
    all_records, summaries = [], {}
    for name in names:
        print(f"\n=== {LABELS[name]} ===")
        recs = evaluate_config(name, CONFIGS[name], questions, client, schema, args)
        all_records += recs
        summaries[name] = summarize(recs)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"results_{stamp}.json").write_text(
        json.dumps({"model": client.model, "summaries": summaries, "records": all_records}, indent=2),
        encoding="utf-8",
    )
    report = RESULTS_DIR / f"report_{stamp}.md"
    write_report(all_records, summaries, report, client.model)

    print("\n" + report.read_text(encoding="utf-8"))
    print(f"\nSaved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()