from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _sample_holdout_failures(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(path):
        is_fail = False
        if "value_ok" in row and isinstance(row.get("value_ok"), bool):
            is_fail = not bool(row.get("value_ok"))
        elif "exact_ok" in row and isinstance(row.get("exact_ok"), bool):
            is_fail = not bool(row.get("exact_ok"))
        elif "row_correct" in row and isinstance(row.get("row_correct"), bool):
            is_fail = not bool(row.get("row_correct"))
        elif "parsed_json" in row and isinstance(row.get("parsed_json"), bool):
            is_fail = not bool(row.get("parsed_json"))
        if not is_fail:
            if row.get("confidence_provided") is False:
                is_fail = True
            if row.get("confidence_proxy_used") is True:
                is_fail = True
        if not is_fail:
            continue
        keep = {
            "id": row.get("id"),
            "family_id": row.get("family_id"),
            "query_type": row.get("query_type"),
            "gold_value": row.get("gold_value"),
            "pred_value": row.get("pred_value"),
            "expected_decision": row.get("expected_decision"),
            "pred_decision": row.get("pred_decision"),
            "confidence": row.get("confidence"),
            "confidence_provided": row.get("confidence_provided"),
            "confidence_proxy_used": row.get("confidence_proxy_used"),
            "parsed_json": row.get("parsed_json"),
            "gold_support_ids": row.get("gold_support_ids"),
            "pred_support_ids": row.get("pred_support_ids"),
        }
        rows.append({k: v for k, v in keep.items() if v is not None})
        if len(rows) >= limit:
            break
    return rows


def _sample_persona_drift(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(path):
        if row.get("invariant") is not False:
            continue
        keep = {
            "id": row.get("id"),
            "persona_base_row_id": row.get("persona_base_row_id"),
            "persona_profile": row.get("persona_profile"),
            "change_reasons": row.get("change_reasons"),
            "canonical_value": row.get("canonical_value"),
            "perturbed_value": row.get("perturbed_value"),
            "canonical_support_ids": row.get("canonical_support_ids"),
            "perturbed_support_ids": row.get("perturbed_support_ids"),
        }
        rows.append({k: v for k, v in keep.items() if v is not None})
        if len(rows) >= limit:
            break
    return rows


def _collect_holdout_failure_ids(path: Path) -> list[str]:
    ids: list[str] = []
    for row in _iter_jsonl(path):
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id.strip():
            continue
        is_fail = False
        if "value_ok" in row and isinstance(row.get("value_ok"), bool):
            is_fail = not bool(row.get("value_ok"))
        elif "exact_ok" in row and isinstance(row.get("exact_ok"), bool):
            is_fail = not bool(row.get("exact_ok"))
        elif "row_correct" in row and isinstance(row.get("row_correct"), bool):
            is_fail = not bool(row.get("row_correct"))
        elif "parsed_json" in row and isinstance(row.get("parsed_json"), bool):
            is_fail = not bool(row.get("parsed_json"))
        if not is_fail:
            if row.get("confidence_provided") is False:
                is_fail = True
            if row.get("confidence_proxy_used") is True:
                is_fail = True
        if is_fail:
            ids.append(row_id.strip())
    # Preserve stable deterministic order (first-seen) while deduping.
    seen: set[str] = set()
    out: list[str] = []
    for row_id in ids:
        if row_id in seen:
            continue
        seen.add(row_id)
        out.append(row_id)
    return out


def _collect_persona_base_failure_ids(path: Path) -> list[str]:
    ids: list[str] = []
    for row in _iter_jsonl(path):
        if row.get("invariant") is not False:
            continue
        base = row.get("persona_base_row_id")
        if not isinstance(base, str):
            continue
        base = base.strip()
        if not base:
            continue
        ids.append(base)
    seen: set[str] = set()
    out: list[str] = []
    for row_id in ids:
        if row_id in seen:
            continue
        seen.add(row_id)
        out.append(row_id)
    return out


def _render_matrix_report(
    matrix: dict[str, Any], matrix_path: Path, sample_limit: int
) -> tuple[str, dict[str, dict[str, list[str]]]]:
    lines: list[str] = []
    row_id_manifest: dict[str, dict[str, list[str]]] = {}
    lines.append("Release Reliability Matrix Failure Report")
    lines.append(f"- matrix_path: {matrix_path}")
    lines.append(f"- status: {matrix.get('status')}")
    lines.append(f"- generated_at_utc: {matrix.get('generated_at_utc')}")

    coverage = matrix.get("coverage") if isinstance(matrix.get("coverage"), dict) else {}
    lines.append(
        "- coverage: required_total={0} produced_total={1} coverage_rate={2}".format(
            coverage.get("required_total"),
            coverage.get("produced_total"),
            coverage.get("coverage_rate"),
        )
    )

    freshness = _as_list(matrix.get("freshness_violations"))
    if freshness:
        lines.append("- freshness_violations:")
        for item in freshness:
            lines.append(f"  - {item}")

    failing_families = _as_list(matrix.get("failing_families"))
    family_rows = {}
    for row in _as_list(matrix.get("families")):
        if isinstance(row, dict) and row.get("id") is not None:
            family_rows[str(row.get("id"))] = row

    for fail in failing_families:
        if not isinstance(fail, dict):
            continue
        family_id = str(fail.get("id"))
        lines.append("")
        lines.append(f"[{family_id}]")
        lines.append(f"- matrix_status: {fail.get('status')}")
        lines.append(f"- matrix_reason: {fail.get('first_failure_reason')}")

        family_row = family_rows.get(family_id, {})
        artifact_path_raw = family_row.get("artifact_path")
        artifact_path = Path(str(artifact_path_raw)) if artifact_path_raw else None
        lines.append(f"- reliability_artifact: {artifact_path_raw}")
        lines.append(f"- stage: {family_row.get('stage')}")
        lines.append(f"- producer_attempted: {family_row.get('producer_attempted')}")
        lines.append(f"- producer_succeeded: {family_row.get('producer_succeeded')}")
        lines.append(f"- produced_in_this_run: {family_row.get('produced_in_this_run')}")
        lines.append(f"- freshness_ok: {family_row.get('freshness_ok')}")
        lines.append(f"- freshness_reason: {family_row.get('freshness_reason')}")

        if not artifact_path or not artifact_path.exists():
            continue

        try:
            reliability = _read_json(artifact_path)
        except Exception:
            lines.append("- reliability_parse_error: true")
            continue

        lines.append(f"- reliability_status: {reliability.get('status')}")
        rel_failures = _as_list(reliability.get("failures"))
        if rel_failures:
            lines.append("- reliability_failures:")
            for reason in rel_failures[:20]:
                lines.append(f"  - {reason}")

        run_dirs = _as_list(reliability.get("runs"))
        if not run_dirs:
            continue
        run_dir = Path(str(run_dirs[0]))
        lines.append(f"- run_dir: {run_dir}")

        holdout_summary_path = run_dir / "holdout_summary.json"
        if holdout_summary_path.exists():
            try:
                holdout = _read_json(holdout_summary_path)
                lines.append(f"- holdout_status: {holdout.get('status')}")
                holdout_failures = _as_list(holdout.get("failures"))
                if holdout_failures:
                    lines.append("- holdout_failures:")
                    for reason in holdout_failures[:20]:
                        lines.append(f"  - {reason}")
            except Exception:
                lines.append("- holdout_parse_error: true")

        persona_summary_path = run_dir / "persona_invariance_summary.json"
        if persona_summary_path.exists():
            try:
                persona = _read_json(persona_summary_path)
                lines.append(
                    "- persona_invariance: status={0} row_invariance_rate={1} rows_changed={2}/{3}".format(
                        persona.get("status"),
                        persona.get("row_invariance_rate"),
                        persona.get("rows_changed"),
                        persona.get("rows_total"),
                    )
                )
            except Exception:
                lines.append("- persona_summary_parse_error: true")

        holdout_rows_path = run_dir / "holdout_rows.jsonl"
        if holdout_rows_path.exists():
            failed_holdout_ids = _collect_holdout_failure_ids(holdout_rows_path)
            row_id_manifest.setdefault(family_id, {})["holdout_failed_ids"] = failed_holdout_ids
            sample_holdout = _sample_holdout_failures(holdout_rows_path, sample_limit)
            if sample_holdout:
                lines.append("- sample_holdout_failures:")
                for row in sample_holdout:
                    lines.append(f"  - {json.dumps(row, ensure_ascii=True)}")
            if failed_holdout_ids:
                lines.append(f"- holdout_failed_row_count: {len(failed_holdout_ids)}")

        persona_rows_path = run_dir / "persona_invariance_rows.jsonl"
        if persona_rows_path.exists():
            failed_persona_base_ids = _collect_persona_base_failure_ids(persona_rows_path)
            row_id_manifest.setdefault(family_id, {})["persona_failed_base_row_ids"] = failed_persona_base_ids
            sample_persona = _sample_persona_drift(persona_rows_path, sample_limit)
            if sample_persona:
                lines.append("- sample_persona_drift:")
                for row in sample_persona:
                    lines.append(f"  - {json.dumps(row, ensure_ascii=True)}")
            if failed_persona_base_ids:
                lines.append(f"- persona_failed_base_row_count: {len(failed_persona_base_ids)}")

    return "\n".join(lines) + "\n", row_id_manifest


def _write_row_id_outputs(rows_out_dir: Path, row_id_manifest: dict[str, dict[str, list[str]]]) -> None:
    rows_out_dir.mkdir(parents=True, exist_ok=True)
    all_holdout: list[str] = []
    all_persona_base: list[str] = []

    for family_id, payload in sorted(row_id_manifest.items(), key=lambda item: item[0]):
        holdout_ids = payload.get("holdout_failed_ids") or []
        persona_base_ids = payload.get("persona_failed_base_row_ids") or []
        if holdout_ids:
            (rows_out_dir / f"{family_id}_holdout_failed_ids.txt").write_text(
                "\n".join(holdout_ids) + "\n",
                encoding="utf-8",
            )
            all_holdout.extend(holdout_ids)
        if persona_base_ids:
            (rows_out_dir / f"{family_id}_persona_failed_base_ids.txt").write_text(
                "\n".join(persona_base_ids) + "\n",
                encoding="utf-8",
            )
            all_persona_base.extend(persona_base_ids)

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    unique_holdout = _dedupe(all_holdout)
    unique_persona_base = _dedupe(all_persona_base)
    combined = _dedupe(unique_holdout + unique_persona_base)

    if unique_holdout:
        (rows_out_dir / "failed_holdout_row_ids.txt").write_text(
            "\n".join(unique_holdout) + "\n",
            encoding="utf-8",
        )
    if unique_persona_base:
        (rows_out_dir / "persona_drift_base_row_ids.txt").write_text(
            "\n".join(unique_persona_base) + "\n",
            encoding="utf-8",
        )
    if combined:
        (rows_out_dir / "failed_row_ids.txt").write_text(
            "\n".join(combined) + "\n",
            encoding="utf-8",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a detailed failure report from release reliability matrix JSON.")
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sample-limit", type=int, default=5)
    parser.add_argument(
        "--rows-out-dir",
        type=Path,
        default=None,
        help="Optional directory to emit machine-readable failed row id lists.",
    )
    return parser.parse_args()


def main() -> int:
    ns = _parse_args()
    try:
        matrix = _read_json(ns.matrix)
    except Exception as exc:
        print(f"Failed to read matrix JSON: {ns.matrix} ({exc})")
        return 1
    if not isinstance(matrix, dict):
        print(f"Invalid matrix payload: {ns.matrix}")
        return 1

    report, row_id_manifest = _render_matrix_report(
        matrix=matrix,
        matrix_path=ns.matrix,
        sample_limit=max(1, ns.sample_limit),
    )
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(report, encoding="utf-8")
    print(f"Wrote {ns.out}")
    if ns.rows_out_dir is not None:
        _write_row_id_outputs(ns.rows_out_dir, row_id_manifest)
        print(f"Wrote row id files under {ns.rows_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
