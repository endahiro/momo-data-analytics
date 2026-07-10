"""
search_comparison.py — compare linear search vs dictionary lookup on the
parsed transaction data.

Task from the assignment:
  - Implement linear search over the list of transactions.
  - Implement dictionary lookup (id -> transaction).
  - Measure/compare efficiency for at least 20 records.
  - Reflect on why one is faster and what could be better.

We run each search N times per method to average out timing noise. Findings
are printed as a table and saved to disk for the PDF report.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import time
from typing import Any


# ---------------------------------------------------------------------------
# Load the parsed transactions produced by parse_xml.py
# ---------------------------------------------------------------------------
HERE       = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(HERE)
DATA_PATH  = os.path.join(REPO_ROOT, "data", "processed", "transactions.json")
OUT_PATH   = os.path.join(REPO_ROOT, "data", "processed", "search_comparison.json")


def load_transactions() -> list[dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# The two search implementations under test.
# ---------------------------------------------------------------------------
def linear_search(transactions: list[dict[str, Any]], target_id: int) -> dict | None:
    """Scan the list from the front until we hit the id or run out. O(n)."""
    for tx in transactions:
        if tx["id"] == target_id:
            return tx
    return None


def dict_lookup(index: dict[int, dict[str, Any]], target_id: int) -> dict | None:
    """Direct hash lookup — average O(1)."""
    return index.get(target_id)


# ---------------------------------------------------------------------------
# Timing harness.
# ---------------------------------------------------------------------------
def time_search(fn, args, repeats: int) -> list[float]:
    """Run `fn(*args)` `repeats` times and return per-call durations in seconds."""
    durations = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn(*args)
        durations.append(time.perf_counter() - t0)
    return durations


def run_comparison(
    transactions: list[dict[str, Any]],
    sample_size: int = 20,
    repeats_per_id: int = 1000,
) -> dict[str, Any]:
    """Pick `sample_size` random ids and time both search methods on each."""

    # Build the dictionary index once, up front.
    index: dict[int, dict[str, Any]] = {t["id"]: t for t in transactions}

    random.seed(42)   # reproducible sample
    target_ids = random.sample(
        [t["id"] for t in transactions],
        k=min(sample_size, len(transactions)),
    )

    linear_times: list[float] = []
    dict_times:   list[float] = []
    per_row: list[dict[str, Any]] = []

    for tid in target_ids:
        lin = time_search(linear_search, (transactions, tid), repeats_per_id)
        dct = time_search(dict_lookup,   (index, tid),        repeats_per_id)

        lin_avg = statistics.mean(lin)
        dct_avg = statistics.mean(dct)

        linear_times.append(lin_avg)
        dict_times.append(dct_avg)
        per_row.append({
            "id": tid,
            "linear_avg_us": lin_avg * 1_000_000,
            "dict_avg_us":   dct_avg * 1_000_000,
            "speedup":       lin_avg / dct_avg if dct_avg else None,
        })

    return {
        "dataset_size":      len(transactions),
        "sample_size":       len(target_ids),
        "repeats_per_id":    repeats_per_id,
        "linear_overall_us": statistics.mean(linear_times) * 1_000_000,
        "dict_overall_us":   statistics.mean(dict_times)   * 1_000_000,
        "speedup_overall":   (statistics.mean(linear_times)
                              / statistics.mean(dict_times)),
        "per_id":            per_row,
    }


# ---------------------------------------------------------------------------
# Reporting.
# ---------------------------------------------------------------------------
def print_report(result: dict[str, Any]) -> None:
    print("=" * 68)
    print("  MoMo Transactions — Search Efficiency Comparison")
    print("=" * 68)
    print(f"  Dataset size:   {result['dataset_size']:>6} transactions")
    print(f"  Sample size:    {result['sample_size']:>6} random ids")
    print(f"  Repeats/id:     {result['repeats_per_id']:>6}")
    print("-" * 68)
    print(f"  {'ID':>6}  {'Linear (µs)':>14}  {'Dict (µs)':>12}  {'Speedup':>10}")
    print("-" * 68)
    for row in result["per_id"]:
        speedup = f"{row['speedup']:.1f}×" if row["speedup"] else "n/a"
        print(f"  {row['id']:>6}  "
              f"{row['linear_avg_us']:>12.3f}    "
              f"{row['dict_avg_us']:>10.3f}    "
              f"{speedup:>10}")
    print("-" * 68)
    print(f"  {'AVG':>6}  "
          f"{result['linear_overall_us']:>12.3f}    "
          f"{result['dict_overall_us']:>10.3f}    "
          f"{result['speedup_overall']:>9.1f}×")
    print("=" * 68)
    print()
    print("Interpretation")
    print("--------------")
    print("Linear search walks the list one item at a time; the further into")
    print("the list the target sits, the more comparisons it takes. For a list")
    print(f"of {result['dataset_size']} items, the average call has to look at")
    print(f"~{result['dataset_size']//2} entries before finding a random target — that's O(n).")
    print()
    print("Dictionary lookup hashes the key and jumps straight to the slot")
    print("that holds it. Cost is (almost) independent of dataset size — O(1)")
    print("average. That's why the dictionary wins by a factor of ~"
          f"{result['speedup_overall']:.0f}× here,")
    print("and the gap grows as the dataset grows.")
    print()
    print("Other options worth considering")
    print("-------------------------------")
    print("* Binary search on a sorted list — O(log n). Faster than linear")
    print("  when the list is already sorted, but still slower than a dict")
    print("  and requires the list to stay sorted after every insert.")
    print("* A B-tree index (as used by MySQL) — O(log n) and works on disk;")
    print("  the right choice once data outgrows memory.")
    print("* A trie or bloom filter — useful for prefix matching or")
    print("  membership checks, not exact lookup by integer id.")


def save_report(result: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


def main() -> int:
    if not os.path.exists(DATA_PATH):
        print(f"Missing {DATA_PATH}. Run `python dsa/parse_xml.py` first.")
        return 1
    txs = load_transactions()
    result = run_comparison(txs)
    print_report(result)
    save_report(result)
    print(f"\nJSON report saved to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
