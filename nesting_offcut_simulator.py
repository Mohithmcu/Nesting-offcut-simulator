

import argparse
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Assumptions (stated, not measured; each one would be confirmed with the
# nesting lead before any real use)
# ---------------------------------------------------------------------------
STEEL_DENSITY_T_PER_MM3 = 7.85e-9   # 7,850 kg/m3
EDGE_MARGIN_MM = 15.0               # unusable border on every sheet
KERF_MM = 4.0                       # plasma kerf allowance around each part
DEFAULT_MIN_OFFCUT_LEN_MM = 600.0   # shortest end strip worth keeping
WEEKS = 26

# Prime plate size by thickness (mm): thinner plate bought in longer lengths.
PRIME_PLATE_SIZES = {
    10: (6000.0, 2000.0),
    12: (6000.0, 2000.0),
    16: (6000.0, 2000.0),
    20: (6000.0, 2500.0),
    25: (6000.0, 2500.0),
    30: (6000.0, 2500.0),
}

# Typical structural plate parts: (length, width, needs grain alignment)
PART_TEMPLATES = [
    (650.0, 450.0, False),    # web stiffener
    (900.0, 600.0, False),    # shear tab
    (1400.0, 800.0, False),   # truss gusset
    (1800.0, 950.0, True),    # splice plate
    (1200.0, 1100.0, True),   # anchor plate
    (800.0, 800.0, True),     # cap plate
    (2200.0, 1400.0, True),   # column base plate
    (400.0, 300.0, False),    # small fitting plate
]
THICKNESS_WEIGHTS = {10: 3, 12: 4, 16: 4, 20: 3, 25: 2, 30: 1}


def tonnes(length: float, width: float, thickness: float) -> float:
    return length * width * thickness * STEEL_DENSITY_T_PER_MM3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Part:
    part_id: str
    project: str
    length: float
    width: float
    thickness: int
    grain: bool

    @property
    def weight(self) -> float:
        return tonnes(self.length, self.width, self.thickness)


@dataclass
class Offcut:
    offcut_id: str
    length: float
    width: float
    thickness: int
    origin_project: str
    created_week: int

    @property
    def weight(self) -> float:
        return tonnes(self.length, self.width, self.thickness)


@dataclass
class Rect:
    x: float
    y: float
    w: float  # along plate length
    h: float  # along plate width

    def contains(self, other: "Rect") -> bool:
        return (other.x >= self.x and other.y >= self.y
                and other.x + other.w <= self.x + self.w
                and other.y + other.h <= self.y + self.h)

    def intersects(self, other: "Rect") -> bool:
        return not (other.x >= self.x + self.w or other.x + other.w <= self.x
                    or other.y >= self.y + self.h or other.y + other.h <= self.y)


class Sheet:
    """One plate (prime or offcut) being nested with a MaxRects packer."""

    def __init__(self, length: float, width: float, thickness: int,
                 source: Optional[Offcut] = None):
        self.length = length
        self.width = width
        self.thickness = thickness
        self.source = source  # None means a new prime plate
        usable = Rect(EDGE_MARGIN_MM, EDGE_MARGIN_MM,
                      length - 2 * EDGE_MARGIN_MM, width - 2 * EDGE_MARGIN_MM)
        self.free: List[Rect] = [usable] if usable.w > 0 and usable.h > 0 else []
        self.placed: List[Tuple[Part, Rect]] = []

    @property
    def weight(self) -> float:
        return tonnes(self.length, self.width, self.thickness)

    def _best_position(self, part: Part) -> Optional[Rect]:
        """Bottom-left, length-first: keep parts towards x = 0 so the end of
        the plate stays free as one clean offcut."""
        options = [(part.length + KERF_MM, part.width + KERF_MM)]
        if not part.grain:
            options.append((part.width + KERF_MM, part.length + KERF_MM))
        best, best_score = None, None
        for w, h in options:
            for fr in self.free:
                if w <= fr.w and h <= fr.h:
                    score = (fr.x + w, fr.y)
                    if best_score is None or score < best_score:
                        best, best_score = Rect(fr.x, fr.y, w, h), score
        return best

    def try_place(self, part: Part) -> bool:
        spot = self._best_position(part)
        if spot is None:
            return False
        new_free: List[Rect] = []
        for fr in self.free:
            if not fr.intersects(spot):
                new_free.append(fr)
                continue
            # Split the free rectangle around the placed part (MaxRects).
            if spot.x > fr.x:
                new_free.append(Rect(fr.x, fr.y, spot.x - fr.x, fr.h))
            if spot.x + spot.w < fr.x + fr.w:
                new_free.append(Rect(spot.x + spot.w, fr.y,
                                     fr.x + fr.w - (spot.x + spot.w), fr.h))
            if spot.y > fr.y:
                new_free.append(Rect(fr.x, fr.y, fr.w, spot.y - fr.y))
            if spot.y + spot.h < fr.y + fr.h:
                new_free.append(Rect(fr.x, spot.y + spot.h, fr.w,
                                     fr.y + fr.h - (spot.y + spot.h)))
        # Drop free rectangles contained in another one.
        self.free = [a for i, a in enumerate(new_free)
                     if not any(j != i and b.contains(a) and (b != a or j < i)
                                for j, b in enumerate(new_free))]
        self.placed.append((part, spot))
        return True

    def used_length(self) -> float:
        """Furthest point along the plate length used by any part."""
        return max(r.x + r.w for _, r in self.placed)


# ---------------------------------------------------------------------------
# Synthetic workload
# ---------------------------------------------------------------------------
def generate_releases(seed: int, n_projects: int = 12) -> Dict[int, List[List[Part]]]:
    """Returns {week: [batch of parts, ...]}; each batch is one drawing release."""
    rng = random.Random(seed)
    thick_values = list(THICKNESS_WEIGHTS)
    releases: Dict[int, List[List[Part]]] = {w: [] for w in range(WEEKS)}
    counter = 0
    for p in range(1, n_projects + 1):
        project = f"PRJ-{p:02d}"
        # Each project uses a few plate thicknesses, not all of them.
        project_thicknesses = rng.sample(thick_values, 3)
        project_weights = [THICKNESS_WEIGHTS[t] for t in project_thicknesses]
        week = rng.randint(0, 12)
        for _ in range(rng.randint(4, 6)):
            if week >= WEEKS:
                break
            batch = []
            for _ in range(rng.randint(40, 100)):
                length, width, grain = rng.choice(PART_TEMPLATES)
                counter += 1
                batch.append(Part(
                    part_id=f"{project}-P{counter:04d}",
                    project=project,
                    length=round(length * rng.uniform(0.9, 1.1), -1),
                    width=round(width * rng.uniform(0.9, 1.1), -1),
                    thickness=rng.choices(project_thicknesses, project_weights)[0],
                    grain=grain,
                ))
            releases[week].append(batch)
            week += rng.randint(1, 3)
    return releases


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
@dataclass
class Result:
    policy: str
    min_offcut_len: float
    parts_t: float = 0.0
    prime_t: float = 0.0
    offcuts_used_t: float = 0.0
    offcuts_used_n: int = 0
    cross_project_t: float = 0.0
    offcuts_kept_t: float = 0.0
    scrap_t: float = 0.0
    stock_end_t: float = 0.0
    stock_end_n: int = 0
    unplaced: int = 0
    prime_sheets: int = 0

    @property
    def prime_per_tonne_parts(self) -> float:
        return self.prime_t / self.parts_t

    @property
    def balance_error_t(self) -> float:
        steel_in = self.prime_t + self.offcuts_used_t
        steel_out = self.parts_t + self.scrap_t + self.offcuts_kept_t
        return steel_in - steel_out


def eligible(offcut: Offcut, project: str, policy: str) -> bool:
    if policy == "no_reuse":
        return False
    if policy == "same_project":
        return offcut.origin_project == project
    return True  # pooled


def simulate(releases: Dict[int, List[List[Part]]], policy: str,
             min_offcut_len: float = DEFAULT_MIN_OFFCUT_LEN_MM) -> Result:
    res = Result(policy=policy, min_offcut_len=min_offcut_len)
    stock: List[Offcut] = []
    offcut_counter = 0

    for week in range(WEEKS):
        for batch in releases[week]:
            project = batch[0].project
            by_thickness: Dict[int, List[Part]] = {}
            for part in batch:
                by_thickness.setdefault(part.thickness, []).append(part)

            for thickness, parts in sorted(by_thickness.items()):
                parts.sort(key=lambda p: p.length * p.width, reverse=True)
                prime_len, prime_wid = PRIME_PLATE_SIZES[thickness]
                open_sheets: List[Sheet] = []

                for part in parts:
                    if any(s.try_place(part) for s in open_sheets):
                        continue
                    # Offcut first: smallest eligible offcut the part fits on.
                    candidates = sorted(
                        (o for o in stock if o.thickness == thickness
                         and eligible(o, project, policy)),
                        key=lambda o: o.length * o.width)
                    placed = False
                    for off in candidates:
                        sheet = Sheet(off.length, off.width, thickness, source=off)
                        if sheet.try_place(part):
                            stock.remove(off)
                            open_sheets.append(sheet)
                            placed = True
                            break
                    if placed:
                        continue
                    sheet = Sheet(prime_len, prime_wid, thickness)
                    if sheet.try_place(part):
                        open_sheets.append(sheet)
                    else:
                        res.unplaced += 1  # larger than a prime plate

                # Close the sheets: book steel in, parts out, offcut or scrap.
                for sheet in open_sheets:
                    if sheet.source is None:
                        res.prime_t += sheet.weight
                        res.prime_sheets += 1
                    else:
                        res.offcuts_used_t += sheet.weight
                        res.offcuts_used_n += 1
                        if sheet.source.origin_project != project:
                            res.cross_project_t += sheet.weight
                    parts_t = sum(p.weight for p, _ in sheet.placed)
                    res.parts_t += parts_t

                    end_len = sheet.length - sheet.used_length()
                    kept_t = 0.0
                    if end_len >= min_offcut_len:
                        offcut_counter += 1
                        off = Offcut(f"OFF-{offcut_counter:04d}", end_len,
                                     sheet.width, thickness, project, week)
                        stock.append(off)
                        kept_t = off.weight
                        res.offcuts_kept_t += kept_t
                    res.scrap_t += sheet.weight - parts_t - kept_t

    res.stock_end_t = sum(o.weight for o in stock)
    res.stock_end_n = len(stock)
    return res


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_policy_table(results: List[Result]) -> None:
    base = results[0]
    print(f"{'Policy':<14}{'Prime t':>10}{'Prime t per':>13}{'vs no_reuse':>13}"
          f"{'Offcuts used':>15}{'of which':>15}{'Scrap t':>10}{'Offcut stock':>17}")
    print(f"{'':<14}{'':>10}{'t of parts':>13}{'':>13}"
          f"{'(n / t)':>15}{'cross-proj t':>15}{'':>10}{'at end (n / t)':>17}")
    print("-" * 108)
    for r in results:
        change = (r.prime_per_tonne_parts / base.prime_per_tonne_parts - 1) * 100
        print(f"{r.policy:<14}{r.prime_t:>10.1f}{r.prime_per_tonne_parts:>13.3f}"
              f"{change:>12.1f}%"
              f"{f'{r.offcuts_used_n} / {r.offcuts_used_t:.1f}':>15}"
              f"{r.cross_project_t:>15.1f}{r.scrap_t:>10.1f}"
              f"{f'{r.stock_end_n} / {r.stock_end_t:.1f}':>17}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--seed", type=int, default=7, help="workload seed")
    args = parser.parse_args()

    releases = generate_releases(args.seed)
    n_parts = sum(len(b) for batches in releases.values() for b in batches)
    n_batches = sum(len(batches) for batches in releases.values())

    print("=" * 108)
    print("Offcut reuse simulator: synthetic plate workload "
          f"(seed {args.seed}, {WEEKS} weeks)")
    print("=" * 108)
    print(f"{n_parts} parts in {n_batches} drawing releases across 12 projects. "
          f"Edge margin {EDGE_MARGIN_MM:.0f} mm, kerf {KERF_MM:.0f} mm, "
          f"minimum offcut length {DEFAULT_MIN_OFFCUT_LEN_MM:.0f} mm.\n")

    policies = ["no_reuse", "same_project", "pooled"]
    results = [simulate(releases, p) for p in policies]

    # Same workload must give the same part tonnage under every policy.
    assert len({round(r.parts_t, 6) for r in results}) == 1
    print(f"Plate parts produced: {results[0].parts_t:.1f} t "
          f"(identical under every policy)\n")

    print("1) Prime plate needed under each reuse policy")
    print_policy_table(results)

    none, same, pooled = results
    same_gain = (1 - same.prime_t / none.prime_t) * 100
    pooled_gain = (1 - pooled.prime_t / none.prime_t) * 100
    extra = (1 - pooled.prime_t / same.prime_t) * 100
    print(f"\n   Same-project reuse needs {same_gain:.1f}% less prime plate than no reuse.")
    print(f"   Pooled reuse needs {pooled_gain:.1f}% less than no reuse, and "
          f"{extra:.1f}% less than same-project reuse.")
    print(f"   That last gap ({same.prime_t - pooled.prime_t:.1f} t here) is what "
          f"the cross-project transfer rule is worth.")
    print(f"   Steel moved between projects under pooling: "
          f"{pooled.cross_project_t:.1f} t. This is the tonnage the cost team "
          f"would need to price.")

    print("\n2) Effect of the minimum offcut length rule (pooled policy)")
    print(f"{'Min length mm':<16}{'Prime t':>10}{'Prime t per t parts':>22}"
          f"{'Offcuts used (n)':>18}{'Offcuts in stock at end (n / t)':>34}")
    print("-" * 100)
    for min_len in (300.0, 600.0, 1200.0, 2000.0):
        r = simulate(releases, "pooled", min_len)
        print(f"{min_len:<16.0f}{r.prime_t:>10.1f}{r.prime_per_tonne_parts:>22.3f}"
              f"{r.offcuts_used_n:>18}{f'{r.stock_end_n} / {r.stock_end_t:.1f}':>34}")
    print("   A low threshold keeps more steel but fills the yard with small pieces")
    print("   to label, store and find. This is the trade-off to agree with the nesting lead.")

    print("\n3) Mass balance check (steel in = parts + scrap + offcuts kept)")
    for r in results:
        status = "OK" if abs(r.balance_error_t) < 1e-6 else "FAILED"
        print(f"   {r.policy:<14} difference {r.balance_error_t:+.6f} t  {status}")
    if any(r.unplaced for r in results):
        print(f"   Note: {results[0].unplaced} parts were larger than a prime plate "
              f"and were skipped.")

    print("\nSynthetic data. Read the relative differences between policies, "
          "not the absolute waste figures.")
    print("=" * 108)


if __name__ == "__main__":
    main()
