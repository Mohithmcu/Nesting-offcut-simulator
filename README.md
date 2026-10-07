# Offcut reuse simulator for plate nesting

A small prototype built alongside a Forward Deployed Engineer case study for a structural steel fabricator. It tests one specific claim from that case study on synthetic data:

> Using offcuts before opening new plates cuts the prime plate needed per tonne of parts, and letting offcuts move **between projects** saves more again. The gap between the two is what a cross-project cost transfer rule is worth.

It is not a product and not a forecast. The data is synthetic, so read the differences between policies rather than the absolute waste figures.

## What it does

1. **Generates a workload.** 12 projects release drawings over 26 weeks. Each project uses three plate thicknesses, and each release is a batch of 40 to 100 typical plate parts (gussets, stiffeners, base plates, splice plates and so on).
2. **Nests the parts.** Each part is placed with a MaxRects packer (bottom-left, length-first). Every sheet has a 15 mm edge margin, every part gets a 4 mm kerf allowance, and parts that need grain alignment are never rotated.
3. **Creates offcuts.** After a sheet is nested, the unused end of the plate is cut off. If it is at least the minimum offcut length (600 mm by default), it goes into stock; otherwise it is scrap.
4. **Compares three policies on the same workload:**

   | Policy | Rule |
   |---|---|
   | `no_reuse` | Offcuts are kept but never used again |
   | `same_project` | An offcut can only be used by the project that created it |
   | `pooled` | Any project can use any offcut of the right thickness |

5. **Checks the books.** Every run is reconciled with a mass balance: steel in (prime plate + offcuts used) must equal steel out (parts + scrap + offcuts kept). This is the same reconciliation a real loss ledger would need before its numbers are trusted.

## How to run

Needs Python 3.8 or later and nothing else (standard library only).

```bash
python nesting_offcut_simulator.py              # default workload, seed 7
python nesting_offcut_simulator.py --seed 11    # a different random workload
```

It runs in under a second. The output of the default run is saved in `sim_output.txt`.

## Results (seed 7)

| Policy | Prime plate (t) | Prime plate per t of parts | Change vs no reuse |
|---|---:|---:|---:|
| no_reuse | 878.8 | 1.469 | 0.0% |
| same_project | 767.6 | 1.283 | -12.7% |
| pooled | 738.0 | 1.233 | -16.0% |

- Same-project reuse needs 12.7% less prime plate than no reuse.
- Pooling needs a further **3.9% less** than same-project reuse (29.7 t on 598 t of parts).
- Pooling moves 101.5 t of offcuts between projects. That is the tonnage a cost team would have to price under a transfer rule.
- The mass balance closes exactly for all three policies.

The result is stable across workloads. Over seeds 7, 11 and 23, pooling saved a further 3.5% to 3.9% over same-project reuse.

**Minimum offcut length (pooled policy).** Lowering the threshold from 600 mm to 300 mm saves almost no extra plate but leaves four times as many small pieces in stock (77 instead of 19). Raising it to 2,000 mm loses about 2% more prime plate. The right threshold is a trade-off between steel saved and yard handling, and it should be agreed with the people who run the nesting and the yard.

## Assumptions

| Item | Value |
|---|---|
| Steel density | 7,850 kg/m³ |
| Edge margin per sheet | 15 mm |
| Kerf allowance per part | 4 mm |
| Default minimum offcut length | 600 mm |
| Prime plate size | 6,000 × 2,000 mm (10–16 mm thick), 6,000 × 2,500 mm (20–30 mm thick) |
| Offcut shape | Full-width strip from the unused end of the plate |

All of these are placeholders. In a real deployment they would come from the fabricator's own cutting rules and stock sizes.

## Limitations

- Parts are rectangles. Real parts have holes, cut-outs and irregular outlines, which a production nester handles and this does not.
- Only the end strip of a plate becomes an offcut. Usable areas elsewhere on the sheet are counted as scrap, so real reuse could be somewhat higher.
- Offcut selection is greedy (the smallest offcut that fits the next part). It shows the effect of the policy, not the best possible allocation.
- It assumes every offcut in stock can be found and is in good condition. In practice some cannot, which is why labelling and rack locations matter.
- It does not model drawing revisions, purchasing lead times or the cost of handling offcuts.

## Files

| File | What it is |
|---|---|
| `nesting_offcut_simulator.py` | The simulator |
| `sim_output.txt` | Output of the default run (seed 7) |
| `README.md` | This file |
