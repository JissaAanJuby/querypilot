"""Stage 1 sanity check: database, read-only mode, and Gemini connection.

Run from the project root: python check_setup.py
"""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv


DB_PATH = Path("data/chinook.db")


def check_database() -> bool:
    if not DB_PATH.exists():
        print(f"[FAIL] Database not found at {DB_PATH.resolve()}")
        return False

    # Open SQLite database in READ-ONLY mode
    uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    ]

    print(f"[OK] Found {len(tables)} tables:")

    for table in tables:
        count = conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]

        print(f"     {table:<16} {count:>6} rows")

    # Prove that writing is blocked
    try:
        conn.execute(
            "CREATE TABLE should_not_exist (id INTEGER)"
        )

        print(
            "[FAIL] Write succeeded, database is NOT read-only!"
        )

        return False

    except sqlite3.OperationalError as e:
        print(f"[OK] Write blocked as expected: {e}")

    finally:
        conn.close()

    return True


def check_gemini() -> bool:
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    if not api_key or api_key == "your_key_here":
        print(
            "[FAIL] GEMINI_API_KEY missing. "
            "Edit your .env file."
        )

        return False

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly one word: ready"
        )

        print(
            f"[OK] Gemini ({model}) replied: "
            f"{response.text.strip()}"
        )

        return True

    except Exception as e:
        print(f"[FAIL] Gemini call failed: {e}")
        return False


if __name__ == "__main__":

    db_ok = check_database()
    gemini_ok = check_gemini()

    print()

    if db_ok and gemini_ok:
        print("STAGE 1 PASSED")
    else:
        print(
            "STAGE 1 NOT COMPLETE, "
            "fix the [FAIL] lines above"
        )