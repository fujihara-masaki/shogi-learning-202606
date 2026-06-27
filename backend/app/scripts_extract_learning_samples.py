from __future__ import annotations

import argparse

from .learning_samples import build_learning_sample_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract balanced learning samples from imported YaneuraOu book data")
    parser.add_argument("--source-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--per-opening-limit", type=int, default=500)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = build_learning_sample_plan(args.source_id, limit=args.limit, per_opening_limit=args.per_opening_limit, seed=args.seed, dry_run=args.dry_run)
    print(f"source_id={plan.source_id} dry_run={plan.dry_run}")
    print(f"candidates={plan.total_candidates} selected={plan.selected_count} unclassified={plan.unclassified_count}")
    for key, summary in sorted(plan.by_opening.items()):
        print(f"{key}\t{summary['opening_name']}\tcandidates={summary['candidate_count']}\tselected={summary['selected_count']}")


if __name__ == "__main__":
    main()
