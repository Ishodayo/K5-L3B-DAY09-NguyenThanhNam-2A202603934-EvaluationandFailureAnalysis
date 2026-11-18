"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    from lab9.graders import GRADERS

    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    safety = {m["id"] for m in spec.get("metrics", []) if m.get("kind") == "safety"}

    # 1. metric values must be real numbers (NaN compares False with every threshold -> passes)
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, bool) or v is None:
            continue
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            problems.append(f"metric {k} = {v!r} is not a finite number")

    # 2. graders must not have crashed, and every graded row value must be a real verdict
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    for m in graded:
        bad = [r for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            problems.append(f"{len(bad)} row(s) with no verdict for {m} (e.g. {bad[0].get('item_id')}@{bad[0].get('seed')}"
                            f" = {bad[0].get(m)!r}): a crashed grader drops out of the mean")

    # 3. coverage: every (item, seed) exactly once, the same set as the baseline, the spec's seeds
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    want_n = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want_n}")
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        problems.append(f"{len(dup)} duplicated (item, seed) row(s), e.g. {dup[0]}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        missing, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra"
                        + (f", e.g. missing {sorted(missing, key=str)[0]}" if missing else ""))
    if man.get("items") != base_man.get("items") or sorted(man.get("seeds") or []) != sorted(base_man.get("seeds") or []):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from baseline "
                        f"{base_man.get('items')}/{base_man.get('seeds')}")
    if spec.get("seeds") and sorted(man.get("seeds") or []) != sorted(spec["seeds"]):
        problems.append(f"report seeds {man.get('seeds')} are not the spec's seeds {spec['seeds']}")

    # 4. the headline numbers must be what the rows say (a hand-edited metric with honest rows)
    for m in graded:
        reported = (pr.get("metrics") or {}).get(m)
        vals = [r[m] for r in rows if isinstance(r.get(m), bool)]
        if reported is None or not vals or isinstance(reported, bool) or not isinstance(reported, (int, float)):
            continue
        want = sum(vals) if m in safety else round(sum(vals) / len(vals), 4)
        if math.isfinite(reported) and abs(reported - want) > 1e-6:
            problems.append(f"metric {m} = {reported} but its rows give {want}")
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        if isinstance(r.get("pass_rate"), bool):
            by_item.setdefault(r["item_id"], []).append(r["pass_rate"])
    for k in spec.get("pass_k") or []:
        for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
            reported = (pr.get("metrics") or {}).get(f"{name}_{k}")
            if not isinstance(reported, (int, float)) or isinstance(reported, bool) or not math.isfinite(reported):
                continue
            if by_item and min(len(v) for v in by_item.values()) >= k:
                est = [fn(len(v), sum(v), k) for v in by_item.values()]
                want = round(sum(est) / len(est), 4)
                if abs(reported - want) > 1e-6:
                    problems.append(f"metric {name}_{k} = {reported} but its rows give {want}")

    # 5. slice tags come from the labels: an item may not leave (or join) a slice in a PR
    def tags(rs: list[dict]) -> dict[str, set[tuple[str, ...]]]:
        out: dict[str, set[tuple[str, ...]]] = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pr_tags, base_tags = tags(rows), tags(base_rows)
    moved = sorted(i for i in pr_tags if i in base_tags and pr_tags[i] != base_tags[i])
    if moved:
        problems.append(f"slice tags of {len(moved)} item(s) differ from baseline, e.g. {moved[0]}: "
                        f"{sorted(pr_tags[moved[0]])} vs {sorted(base_tags[moved[0]])}")

    # 6. ratchet: on the same eval-set version a spec may only get stricter
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _looser(name: str, new: dict, old: dict) -> list[str]:
    """Compare one metric or slice rule; return what got looser."""
    out = []
    nt, ot = new.get("threshold", new), old.get("threshold", old)
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{name}: blocking -> non-blocking")
    if "max" in ot and ("max" not in nt or nt["max"] > ot["max"]):
        out.append(f"{name}: max {ot['max']} -> {nt.get('max')}")
    if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
        out.append(f"{name}: min {ot['min']} -> {nt.get('min')}")
    if "max_increase" in ot and ("max_increase" not in nt or nt["max_increase"] > ot["max_increase"]):
        out.append(f"{name}: max_increase {ot['max_increase']} -> {nt.get('max_increase')}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append(f"{name}: no_significant_drop dropped")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out: list[str] = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new_m:
            out.append(f"ratchet: metric {m['id']} removed")
        else:
            out += [f"ratchet: {p}" for p in _looser(m["id"], new_m[m["id"]], m)]
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s["name"], s["metric"])
        if key not in new_s:
            out.append(f"ratchet: slice {key[0]}/{key[1]} removed")
        else:
            out += [f"ratchet: {p}" for p in _looser(f"slice:{key[0]}/{key[1]}", new_s[key], s)]
    if set(spec.get("seeds") or []) < set(base_spec.get("seeds") or []) or \
            len(spec.get("seeds") or []) < len(base_spec.get("seeds") or []):
        out.append(f"ratchet: seeds {base_spec.get('seeds')} -> {spec.get('seeds')}")
    ob, nb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if nb.get("confidence", 0.95) < ob.get("confidence", 0.95):
        out.append(f"ratchet: bootstrap confidence {ob.get('confidence')} -> {nb.get('confidence')}")
    if set(base_spec.get("pass_k") or []) - set(spec.get("pass_k") or []):
        out.append(f"ratchet: pass_k {base_spec.get('pass_k')} -> {spec.get('pass_k')}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        if not a:
            # A slice the spec names but the PR has no rows for cannot be "fine": treat as missing.
            verdict, val, note = "missing", None, "no rows in slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            verdict, note = "ok", f"n={len(a)} item"
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027))
                    note = f"n={len(keys)} Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
