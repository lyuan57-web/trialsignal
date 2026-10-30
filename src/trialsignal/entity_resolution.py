"""Traceable sponsor entity resolution with abstention for ambiguous matches."""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from .normalize import normalize_sponsor


@dataclass(frozen=True)
class Resolution:
    query: str
    normalized_query: str
    canonical_name: str | None
    score: float
    runner_up_score: float
    margin: float
    method: str
    accepted: bool

    def to_dict(self) -> dict:
        return asdict(self)


class SponsorResolver:
    """Resolve aliases while refusing low-confidence or ambiguous matches."""

    def __init__(self, canonical_names: Iterable[str], threshold: float = 90, margin: float = 5):
        names = sorted({name.strip() for name in canonical_names if name.strip()})
        self.threshold = threshold
        self.margin = margin
        self._normalized_to_names: dict[str, list[str]] = {}
        for name in names:
            self._normalized_to_names.setdefault(normalize_sponsor(name), []).append(name)
        self._keys = list(self._normalized_to_names)

    @classmethod
    def from_database(cls, path: str | Path, **kwargs: float) -> SponsorResolver:
        with sqlite3.connect(path) as connection:
            names = [row[0] for row in connection.execute("SELECT canonical_name FROM sponsors")]
        return cls(names, **kwargs)

    def resolve(self, query: str) -> Resolution:
        normalized = normalize_sponsor(query)
        if not normalized or not self._keys:
            return Resolution(query, normalized, None, 0, 0, 0, "no_candidate", False)

        if normalized in self._normalized_to_names:
            canonical = self._normalized_to_names[normalized][0]
            return Resolution(query, normalized, canonical, 100, 0, 100, "exact_normalized", True)

        candidates = process.extract(normalized, self._keys, scorer=fuzz.WRatio, limit=2)
        best_key, best_score, _ = candidates[0]
        runner_up = float(candidates[1][1]) if len(candidates) > 1 else 0.0
        score = float(best_score)
        score_margin = score - runner_up
        accepted = score >= self.threshold and score_margin >= self.margin
        return Resolution(
            query=query,
            normalized_query=normalized,
            canonical_name=self._normalized_to_names[best_key][0] if accepted else None,
            score=round(score, 2),
            runner_up_score=round(runner_up, 2),
            margin=round(score_margin, 2),
            method="fuzzy" if accepted else "abstain",
            accepted=accepted,
        )


def evaluate_labels(path: str | Path, resolver: SponsorResolver) -> dict[str, float | int]:
    """Evaluate a CSV containing alias,canonical_name columns."""
    total = correct = accepted = 0
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            result = resolver.resolve(row["alias"])
            accepted += int(result.accepted)
            correct += int(
                result.accepted
                and normalize_sponsor(result.canonical_name)
                == normalize_sponsor(row["canonical_name"])
            )
    return {
        "labeled_pairs": total,
        "accepted": accepted,
        "correct": correct,
        "precision_on_accepted": correct / accepted if accepted else 0.0,
        "coverage": accepted / total if total else 0.0,
    }
