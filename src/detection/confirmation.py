from __future__ import annotations

import dataclasses
from collections import Counter

from src.detection.pipeline import PlateReadEvent
from src.utils.plate_normalizer import latin_to_arabic


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    row = list(range(len(b) + 1))
    for c_a in a:
        new_row = [row[0] + 1]
        for j, c_b in enumerate(b):
            new_row.append(min(
                row[j] + (c_a != c_b),  # substitution
                row[j + 1] + 1,          # deletion
                new_row[-1] + 1,         # insertion
            ))
        row = new_row
    return row[-1]


class _Cluster:
    """Tracks a group of fuzzy-similar plate readings for one plate bbox."""

    def __init__(self, representative: str) -> None:
        # First reading that anchored this cluster; used as the fuzzy-match key.
        self.representative = representative
        self.hits: int = 0
        self.readings: Counter[str] = Counter()
        self.latin_readings: Counter[str] = Counter()
        self.last_event: PlateReadEvent | None = None
        self.confirmed: bool = False

    def add(self, key: str, event: PlateReadEvent, min_hits: int) -> None:
        self.hits += 1
        self.readings[key] += 1
        # Only count non-empty latin readings so empty strings don't win by plurality.
        if event.latin_part:
            self.latin_readings[event.latin_part] += 1
        self.last_event = event
        if self.hits >= min_hits:
            self.confirmed = True

    def best_event(self) -> PlateReadEvent:
        """Return the latest event with all fields replaced by majority-vote values."""
        assert self.last_event is not None
        best_digits = self.readings.most_common(1)[0][0]
        best_latin = self.latin_readings.most_common(1)[0][0] if self.latin_readings else ""
        best_arabic = latin_to_arabic(best_latin) if best_latin else self.last_event.arabic_part
        # Keep Arabic as a structured field; the exported plate number is English-only.
        plate_parts = [p for p in (best_digits, best_latin) if p]
        best_plate_number = " ".join(plate_parts)
        return dataclasses.replace(
            self.last_event,
            plate_number=best_plate_number,
            numeric_part=best_digits,
            latin_part=best_latin,
            arabic_part=best_arabic,
        )


class ConfirmationFilter:
    """Gate plate events until a plate has accumulated *min_hits* detections.

    Unlike a streak-based approach, readings are grouped by **fuzzy similarity**
    (Levenshtein distance ≤ *fuzzy_threshold*).  OCR variants of the same plate
    (e.g. ``3327`` / ``3337`` / ``337``) all land in the same cluster and each
    contribute one hit.  Once *min_hits* total readings accumulate, the
    **majority-vote** digit string is emitted — so the most-seen reading wins
    regardless of per-frame noise.

    The cluster is cleared as soon as the plate is absent for one frame, so a
    returning car always goes through the full confirmation window.

    Usage::

        filt = ConfirmationFilter(min_hits=3, fuzzy_threshold=2)
        confirmed_events = filt.update(camera_id, raw_events)
    """

    def __init__(self, min_hits: int = 3, fuzzy_threshold: int = 2) -> None:
        self.min_hits = min_hits
        self.fuzzy_threshold = fuzzy_threshold
        # {camera_id: list[_Cluster]}
        self._clusters: dict[int, list[_Cluster]] = {}

    def update(self, camera_id: int, events: list[PlateReadEvent]) -> list[PlateReadEvent]:
        """Return only events whose plate cluster has reached *min_hits* detections."""
        clusters = self._clusters.setdefault(camera_id, [])
        active_ids: set[int] = set()

        for event in events:
            key = self._key(event)
            cluster = self._find_cluster(clusters, key)
            if cluster is None:
                cluster = _Cluster(key)
                clusters.append(cluster)
            cluster.add(key, event, self.min_hits)
            active_ids.add(id(cluster))

        # Drop clusters for plates absent this frame.
        self._clusters[camera_id] = [c for c in clusters if id(c) in active_ids]

        return [c.best_event() for c in self._clusters[camera_id] if c.confirmed]

    def _find_cluster(self, clusters: list[_Cluster], key: str) -> _Cluster | None:
        """Return the closest cluster within *fuzzy_threshold*, or None."""
        best: _Cluster | None = None
        best_dist = self.fuzzy_threshold + 1
        for cluster in clusters:
            d = _levenshtein(key, cluster.representative)
            if d <= self.fuzzy_threshold and d < best_dist:
                best_dist = d
                best = cluster
        return best

    @staticmethod
    def _key(event: PlateReadEvent) -> str:
        return event.numeric_part or event.plate_number
