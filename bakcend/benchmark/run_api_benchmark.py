#!/usr/bin/env python3
"""Presentation-ready API benchmark harness for Vaani Connect backend."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slugify(value: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-") or "run"


def _to_bool(value: str | bool | None, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[int(rank)])
    weight = rank - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _latency_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "count": 0,
            "min_ms": None,
            "max_ms": None,
            "mean_ms": None,
            "stdev_ms": None,
            "p50_ms": None,
            "p90_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }
    return {
        "count": len(values),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
        "mean_ms": round(statistics.mean(values), 2),
        "stdev_ms": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "p50_ms": round(_percentile(values, 50) or 0.0, 2),
        "p90_ms": round(_percentile(values, 90) or 0.0, 2),
        "p95_ms": round(_percentile(values, 95) or 0.0, 2),
        "p99_ms": round(_percentile(values, 99) or 0.0, 2),
    }


def _round_or_none(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _safe_json(response: requests.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class TextCase:
    case_id: str
    source_language: str
    target_language: str
    text: str
    include_speech: bool


def _load_dataset(path: Path) -> list[TextCase]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Dataset has no header row: {path}")

        required = {"source_language", "target_language", "text"}
        missing = required - set(name.strip() for name in reader.fieldnames)
        if missing:
            raise ValueError(f"Dataset missing required columns: {', '.join(sorted(missing))}")

        cases: list[TextCase] = []
        for index, row in enumerate(reader, start=1):
            src = (row.get("source_language") or "").strip()
            tgt = (row.get("target_language") or "").strip()
            text = (row.get("text") or "").strip()
            if not src or not tgt or not text:
                raise ValueError(
                    f"Invalid row {index}: source_language, target_language, and text must be non-empty."
                )
            case_id = (row.get("case_id") or f"case-{index:03d}").strip()
            include_speech = _to_bool(row.get("include_speech"), default=False)
            cases.append(
                TextCase(
                    case_id=case_id,
                    source_language=src,
                    target_language=tgt,
                    text=text,
                    include_speech=include_speech,
                )
            )

    if not cases:
        raise ValueError(f"Dataset has no cases: {path}")
    return cases


class _ThreadLocalSession:
    def __init__(self, timeout_s: float, api_key: str | None):
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self.local, "session", None)
        if session is None:
            session = requests.Session()
            setattr(self.local, "session", session)
        return session

    def post_json(self, url: str, payload: dict[str, Any]) -> requests.Response:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return self._session().post(url, json=payload, headers=headers, timeout=self.timeout_s)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return self._session().get(url, params=params or {}, headers=headers, timeout=self.timeout_s)


def _execute_text_request(
    client: _ThreadLocalSession,
    base_url: str,
    run_id: str,
    sequence_id: int,
    run_iteration: int,
    case: TextCase,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    started_perf = time.perf_counter()
    payload = {
        "text": case.text,
        "source_language": case.source_language,
        "target_language": case.target_language,
        "include_speech": case.include_speech,
    }

    row: dict[str, Any] = {
        "run_id": run_id,
        "sequence_id": sequence_id,
        "run_iteration": run_iteration,
        "case_id": case.case_id,
        "source_language": case.source_language,
        "target_language": case.target_language,
        "include_speech": case.include_speech,
        "input_chars": len(case.text),
        "input_bytes_utf8": len(case.text.encode("utf-8")),
        "started_at_utc": started_at,
        "ended_at_utc": None,
        "client_latency_ms": None,
        "status_code": None,
        "success": False,
        "error_type": None,
        "error_detail": None,
        "request_id": None,
        "translated_chars": None,
        "audio_url_present": False,
    }

    try:
        response = client.post_json(f"{base_url}/translate/text", payload)
        ended_at = _utc_now_iso()
        client_latency_ms = (time.perf_counter() - started_perf) * 1000.0
        body = _safe_json(response)

        row["ended_at_utc"] = ended_at
        row["client_latency_ms"] = _round_or_none(client_latency_ms)
        row["status_code"] = response.status_code
        row["request_id"] = body.get("request_id")

        if response.status_code == 200:
            translated_text = body.get("translated_text", "")
            row["success"] = True
            row["translated_chars"] = len(translated_text) if isinstance(translated_text, str) else None
            row["audio_url_present"] = bool(body.get("audio_url"))
            return row

        row["error_type"] = f"http_{response.status_code}"
        detail = body.get("detail")
        row["error_detail"] = str(detail) if detail is not None else response.text[:300]
        return row
    except requests.Timeout:
        row["ended_at_utc"] = _utc_now_iso()
        row["client_latency_ms"] = _round_or_none((time.perf_counter() - started_perf) * 1000.0)
        row["error_type"] = "timeout"
        row["error_detail"] = "Request timed out."
        return row
    except requests.RequestException as exc:
        row["ended_at_utc"] = _utc_now_iso()
        row["client_latency_ms"] = _round_or_none((time.perf_counter() - started_perf) * 1000.0)
        row["error_type"] = "request_exception"
        row["error_detail"] = str(exc)
        return row


def _flatten_metric(metric: dict[str, Any]) -> dict[str, Any]:
    translation = metric.get("translation", {}) if isinstance(metric.get("translation"), dict) else {}
    steps = translation.get("steps") if isinstance(translation.get("steps"), list) else []
    tts = metric.get("tts", {}) if isinstance(metric.get("tts"), dict) else {}
    asr = metric.get("asr", {}) if isinstance(metric.get("asr"), dict) else {}

    def _sum_from_steps(key: str) -> float | None:
        values = [step.get(key) for step in steps if isinstance(step, dict) and isinstance(step.get(key), (int, float))]
        if not values:
            return None
        return round(sum(float(v) for v in values), 2)

    model_ids = translation.get("model_ids")
    if isinstance(model_ids, list):
        model_ids_value = "|".join(str(item) for item in model_ids)
    elif model_ids is None:
        model_ids_value = None
    else:
        model_ids_value = str(model_ids)

    return {
        "metrics_found": True,
        "metric_event": metric.get("event"),
        "metric_logged_at": metric.get("logged_at"),
        "metric_total_latency_ms": _round_or_none(metric.get("total_latency_ms")),
        "metric_translation_route": translation.get("route"),
        "metric_translation_model_ids": model_ids_value,
        "metric_translation_used_fallback": translation.get("used_fallback"),
        "metric_translation_total_ms": _round_or_none(translation.get("total_latency_ms")),
        "metric_translation_step_count": len(steps),
        "metric_translation_preprocess_ms_sum": _sum_from_steps("preprocess_ms"),
        "metric_translation_tokenize_ms_sum": _sum_from_steps("tokenize_ms"),
        "metric_translation_generate_ms_sum": _sum_from_steps("generate_ms"),
        "metric_translation_decode_ms_sum": _sum_from_steps("decode_ms"),
        "metric_tts_latency_ms": _round_or_none(tts.get("latency_ms")),
        "metric_tts_audio_generated": tts.get("audio_generated"),
        "metric_asr_route": asr.get("route"),
        "metric_asr_model_id": asr.get("model_id"),
        "metric_asr_latency_ms": _round_or_none(asr.get("latency_ms")),
    }


def _fetch_recent_metrics(
    client: _ThreadLocalSession,
    base_url: str,
    fetch_limit: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, str | None]:
    try:
        response = client.get_json(f"{base_url}/metrics/recent", params={"limit": fetch_limit})
    except requests.RequestException as exc:
        return {}, None, f"Failed to call /metrics/recent: {exc}"

    body = _safe_json(response)
    if response.status_code != 200:
        detail = body.get("detail", response.text[:200])
        return {}, body, f"/metrics/recent returned HTTP {response.status_code}: {detail}"

    items = body.get("items")
    if not isinstance(items, list):
        return {}, body, "/metrics/recent response did not include an items list."

    by_request_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        request_id = item.get("request_id")
        if isinstance(request_id, str) and request_id:
            by_request_id[request_id] = item

    return by_request_id, body, None


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _summarize_pair(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, bool], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("source_language") or ""),
            str(row.get("target_language") or ""),
            bool(row.get("include_speech")),
        )
        groups.setdefault(key, []).append(row)

    summary: list[dict[str, Any]] = []
    for (src, tgt, include_speech), group in sorted(groups.items(), key=lambda item: item[0]):
        successes = [r for r in group if r.get("success")]
        success_rate = (len(successes) / len(group) * 100.0) if group else 0.0
        client_lat = [float(r["client_latency_ms"]) for r in successes if isinstance(r.get("client_latency_ms"), (int, float))]
        server_lat = [float(r["metric_total_latency_ms"]) for r in successes if isinstance(r.get("metric_total_latency_ms"), (int, float))]

        summary.append(
            {
                "source_language": src,
                "target_language": tgt,
                "include_speech": include_speech,
                "requests": len(group),
                "successes": len(successes),
                "success_rate_pct": round(success_rate, 2),
                "client_p50_ms": _round_or_none(_percentile(client_lat, 50)),
                "client_p95_ms": _round_or_none(_percentile(client_lat, 95)),
                "client_mean_ms": _round_or_none(statistics.mean(client_lat) if client_lat else None),
                "server_p50_ms": _round_or_none(_percentile(server_lat, 50)),
                "server_p95_ms": _round_or_none(_percentile(server_lat, 95)),
                "server_mean_ms": _round_or_none(statistics.mean(server_lat) if server_lat else None),
            }
        )
    return summary


def _summarize_routes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        route = row.get("metric_translation_route")
        if isinstance(route, str) and route:
            counts[route] = counts.get(route, 0) + 1
    total = sum(counts.values())
    summary: list[dict[str, Any]] = []
    for route, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        summary.append(
            {
                "translation_route": route,
                "requests": count,
                "share_pct": round((count / total * 100.0), 2) if total else 0.0,
            }
        )
    return summary


def _summarize_errors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.get("success"):
            continue
        error_type = str(row.get("error_type") or "unknown")
        status_code = str(row.get("status_code") or "")
        key = (error_type, status_code)
        counts[key] = counts.get(key, 0) + 1

    summary: list[dict[str, Any]] = []
    for (error_type, status_code), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        summary.append(
            {
                "error_type": error_type,
                "status_code": status_code,
                "requests": count,
            }
        )
    return summary


def _build_summary(
    rows: list[dict[str, Any]],
    duration_s: float,
    metrics_lookup_size: int,
    metrics_missing: int,
    config: dict[str, Any],
    metrics_warning: str | None,
) -> dict[str, Any]:
    total = len(rows)
    successes = [row for row in rows if row.get("success")]
    failures = total - len(successes)
    success_rate_pct = round((len(successes) / total * 100.0), 2) if total else 0.0
    throughput_rps = round(total / duration_s, 3) if duration_s > 0 else 0.0

    client_latencies = [
        float(row["client_latency_ms"])
        for row in successes
        if isinstance(row.get("client_latency_ms"), (int, float))
    ]
    server_latencies = [
        float(row["metric_total_latency_ms"])
        for row in successes
        if isinstance(row.get("metric_total_latency_ms"), (int, float))
    ]

    return {
        "generated_at_utc": _utc_now_iso(),
        "config": config,
        "totals": {
            "requests": total,
            "successes": len(successes),
            "failures": failures,
            "success_rate_pct": success_rate_pct,
            "duration_s": round(duration_s, 2),
            "throughput_rps": throughput_rps,
        },
        "metrics_join": {
            "joined_requests": metrics_lookup_size - metrics_missing,
            "missing_requests": metrics_missing,
            "warning": metrics_warning,
        },
        "client_latency_ms": _latency_stats(client_latencies),
        "server_total_latency_ms": _latency_stats(server_latencies),
        "pair_summary": _summarize_pair(rows),
        "route_summary": _summarize_routes(rows),
        "error_summary": _summarize_errors(rows),
    }


def _render_markdown(summary: dict[str, Any], files: dict[str, Path]) -> str:
    totals = summary["totals"]
    client = summary["client_latency_ms"]
    server = summary["server_total_latency_ms"]
    config = summary["config"]
    metrics_join = summary["metrics_join"]

    lines: list[str] = []
    lines.append("# Vaani Connect API Benchmark Report")
    lines.append("")
    lines.append(f"- Generated: `{summary['generated_at_utc']}`")
    lines.append(f"- Run ID: `{config['run_id']}`")
    lines.append(f"- Base URL: `{config['base_url']}`")
    lines.append(f"- Dataset: `{config['dataset_path']}`")
    lines.append(f"- Cases: `{config['case_count']}`")
    lines.append(f"- Runs per case: `{config['runs_per_case']}`")
    lines.append(f"- Concurrency: `{config['concurrency']}`")
    lines.append(f"- Include speech mix: `{config['speech_mix']}`")
    lines.append("")
    lines.append("## Headline KPIs")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total requests | {totals['requests']} |")
    lines.append(f"| Successes | {totals['successes']} |")
    lines.append(f"| Failures | {totals['failures']} |")
    lines.append(f"| Success rate | {totals['success_rate_pct']}% |")
    lines.append(f"| Duration | {totals['duration_s']} s |")
    lines.append(f"| Throughput | {totals['throughput_rps']} req/s |")
    lines.append("")
    lines.append("## Client Latency (ms)")
    lines.append("")
    lines.append("| p50 | p90 | p95 | p99 | mean | min | max |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| {client['p50_ms']} | {client['p90_ms']} | {client['p95_ms']} | {client['p99_ms']} "
        f"| {client['mean_ms']} | {client['min_ms']} | {client['max_ms']} |"
    )
    lines.append("")
    lines.append("## Server Total Latency (ms, from /metrics/recent)")
    lines.append("")
    lines.append("| p50 | p90 | p95 | p99 | mean | min | max |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| {server['p50_ms']} | {server['p90_ms']} | {server['p95_ms']} | {server['p99_ms']} "
        f"| {server['mean_ms']} | {server['min_ms']} | {server['max_ms']} |"
    )
    lines.append("")
    lines.append("## Metrics Join Health")
    lines.append("")
    lines.append(f"- Joined requests with backend metrics: `{metrics_join['joined_requests']}`")
    lines.append(f"- Missing backend metrics: `{metrics_join['missing_requests']}`")
    if metrics_join.get("warning"):
        lines.append(f"- Warning: {metrics_join['warning']}")
    lines.append("")
    lines.append("## Route Distribution")
    lines.append("")
    lines.append("| Route | Requests | Share |")
    lines.append("|---|---:|---:|")
    route_summary = summary.get("route_summary", [])
    if route_summary:
        for row in route_summary:
            lines.append(f"| {row['translation_route']} | {row['requests']} | {row['share_pct']}% |")
    else:
        lines.append("| n/a | 0 | 0.0% |")
    lines.append("")
    lines.append("## Language Pair Summary")
    lines.append("")
    lines.append("| Source | Target | Speech | Requests | Success | Client p50 | Client p95 | Server p50 | Server p95 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in summary.get("pair_summary", []):
        lines.append(
            f"| {row['source_language']} | {row['target_language']} | {row['include_speech']} "
            f"| {row['requests']} | {row['success_rate_pct']}% | {row['client_p50_ms']} "
            f"| {row['client_p95_ms']} | {row['server_p50_ms']} | {row['server_p95_ms']} |"
        )
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    lines.append("| Error Type | Status | Requests |")
    lines.append("|---|---:|---:|")
    errors = summary.get("error_summary", [])
    if errors:
        for row in errors:
            lines.append(f"| {row['error_type']} | {row['status_code']} | {row['requests']} |")
    else:
        lines.append("| none | - | 0 |")
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    lines.append(f"- Raw request-level CSV: `{files['raw_requests'].name}`")
    lines.append(f"- Pair summary CSV: `{files['pair_summary'].name}`")
    lines.append(f"- Route summary CSV: `{files['route_summary'].name}`")
    lines.append(f"- Error summary CSV: `{files['error_summary'].name}`")
    lines.append(f"- Summary JSON: `{files['summary_json'].name}`")
    return "\n".join(lines) + "\n"


def _detect_speech_mix(cases: list[TextCase]) -> str:
    if all(case.include_speech for case in cases):
        return "all_true"
    if not any(case.include_speech for case in cases):
        return "all_false"
    return "mixed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Vaani Connect /translate/text API.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: %(default)s).",
    )
    parser.add_argument(
        "--dataset",
        default="benchmark/datasets/presentation_text_cases.csv",
        help="CSV dataset path with text benchmark cases.",
    )
    parser.add_argument(
        "--runs-per-case",
        type=int,
        default=5,
        help="How many times to run each dataset case (default: %(default)s).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent workers (default: %(default)s).",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for each request (default: %(default)s).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key for X-API-Key header.",
    )
    parser.add_argument(
        "--out-dir",
        default="benchmark/results",
        help="Directory where run artifacts are saved (default: %(default)s).",
    )
    parser.add_argument(
        "--tag",
        default="presentation",
        help="Short tag included in output folder name (default: %(default)s).",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Shuffle request order before sending.",
    )
    parser.add_argument(
        "--metrics-fetch-limit",
        type=int,
        default=500,
        help="Limit used when pulling /metrics/recent after run (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs_per_case <= 0:
        raise SystemExit("--runs-per-case must be > 0")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.metrics_fetch_limit <= 0:
        raise SystemExit("--metrics-fetch-limit must be > 0")

    dataset_path = Path(args.dataset).resolve()
    cases = _load_dataset(dataset_path)
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{_slugify(args.tag)}"
    run_dir = Path(args.out_dir).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    requests_plan: list[tuple[int, int, TextCase]] = []
    sequence = 0
    for run_iteration in range(1, args.runs_per_case + 1):
        for case in cases:
            sequence += 1
            requests_plan.append((sequence, run_iteration, case))

    if args.shuffle:
        random.shuffle(requests_plan)

    client = _ThreadLocalSession(timeout_s=args.timeout_s, api_key=args.api_key)

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                _execute_text_request,
                client,
                args.base_url.rstrip("/"),
                run_id,
                sequence_id,
                run_iteration,
                case,
            )
            for (sequence_id, run_iteration, case) in requests_plan
        ]
        for future in as_completed(futures):
            rows.append(future.result())
    duration_s = time.perf_counter() - started

    rows.sort(key=lambda row: int(row["sequence_id"]))

    success_with_id = [
        row for row in rows if row.get("success") and isinstance(row.get("request_id"), str) and row.get("request_id")
    ]
    expected_metrics = len(success_with_id)
    fetch_limit = max(args.metrics_fetch_limit, expected_metrics + 20)
    metrics_by_request_id, metrics_payload, metrics_warning = _fetch_recent_metrics(
        client=client,
        base_url=args.base_url.rstrip("/"),
        fetch_limit=fetch_limit,
    )

    joined_count = 0
    for row in rows:
        row.setdefault("metrics_found", False)
        request_id = row.get("request_id")
        metric = metrics_by_request_id.get(request_id) if isinstance(request_id, str) else None
        if metric is None:
            continue
        row.update(_flatten_metric(metric))
        joined_count += 1

    missing_metrics = max(0, expected_metrics - joined_count)
    capacity = metrics_payload.get("capacity") if isinstance(metrics_payload, dict) else None
    if missing_metrics > 0 and isinstance(capacity, int) and capacity < expected_metrics:
        capacity_warning = (
            f"Only {capacity} metrics events retained in backend memory. "
            f"Increase VAANI_RECENT_METRICS_LIMIT for larger runs."
        )
        metrics_warning = f"{metrics_warning} {capacity_warning}".strip() if metrics_warning else capacity_warning

    config = {
        "run_id": run_id,
        "base_url": args.base_url.rstrip("/"),
        "dataset_path": str(dataset_path),
        "case_count": len(cases),
        "runs_per_case": args.runs_per_case,
        "planned_requests": len(requests_plan),
        "concurrency": args.concurrency,
        "timeout_s": args.timeout_s,
        "shuffle": args.shuffle,
        "speech_mix": _detect_speech_mix(cases),
        "metrics_fetch_limit": fetch_limit,
        "api_key_enabled": bool(args.api_key),
    }

    summary = _build_summary(
        rows=rows,
        duration_s=duration_s,
        metrics_lookup_size=joined_count + missing_metrics,
        metrics_missing=missing_metrics,
        config=config,
        metrics_warning=metrics_warning,
    )

    raw_fields = [
        "run_id",
        "sequence_id",
        "run_iteration",
        "case_id",
        "source_language",
        "target_language",
        "include_speech",
        "input_chars",
        "input_bytes_utf8",
        "translated_chars",
        "audio_url_present",
        "status_code",
        "success",
        "error_type",
        "error_detail",
        "started_at_utc",
        "ended_at_utc",
        "client_latency_ms",
        "request_id",
        "metrics_found",
        "metric_event",
        "metric_logged_at",
        "metric_total_latency_ms",
        "metric_translation_route",
        "metric_translation_model_ids",
        "metric_translation_used_fallback",
        "metric_translation_total_ms",
        "metric_translation_step_count",
        "metric_translation_preprocess_ms_sum",
        "metric_translation_tokenize_ms_sum",
        "metric_translation_generate_ms_sum",
        "metric_translation_decode_ms_sum",
        "metric_tts_latency_ms",
        "metric_tts_audio_generated",
        "metric_asr_route",
        "metric_asr_model_id",
        "metric_asr_latency_ms",
    ]

    pair_summary = summary["pair_summary"]
    route_summary = summary["route_summary"]
    error_summary = summary["error_summary"]

    files = {
        "raw_requests": run_dir / "raw_requests.csv",
        "pair_summary": run_dir / "pair_summary.csv",
        "route_summary": run_dir / "route_summary.csv",
        "error_summary": run_dir / "error_summary.csv",
        "summary_json": run_dir / "summary.json",
        "summary_md": run_dir / "summary.md",
        "run_config_json": run_dir / "run_config.json",
    }

    _write_csv(files["raw_requests"], rows, raw_fields)
    _write_csv(
        files["pair_summary"],
        pair_summary,
        [
            "source_language",
            "target_language",
            "include_speech",
            "requests",
            "successes",
            "success_rate_pct",
            "client_p50_ms",
            "client_p95_ms",
            "client_mean_ms",
            "server_p50_ms",
            "server_p95_ms",
            "server_mean_ms",
        ],
    )
    _write_csv(files["route_summary"], route_summary, ["translation_route", "requests", "share_pct"])
    _write_csv(files["error_summary"], error_summary, ["error_type", "status_code", "requests"])

    with files["summary_json"].open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    with files["run_config_json"].open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    report_markdown = _render_markdown(summary=summary, files=files)
    files["summary_md"].write_text(report_markdown, encoding="utf-8")

    print(f"Benchmark completed: {run_id}")
    print(f"Results directory: {run_dir}")
    print(f"Summary report: {files['summary_md']}")
    print(f"Raw CSV: {files['raw_requests']}")
    if metrics_warning:
        print(f"Metrics warning: {metrics_warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
