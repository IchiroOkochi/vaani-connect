#!/usr/bin/env python3
"""Render presentation-ready graphs for one benchmark results folder."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

try:
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover - import guard for user environment
    raise SystemExit(
        "matplotlib is required for graph rendering. Install it with: pip install matplotlib"
    ) from exc


def _to_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _resolve_results_dir(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()

    nested = (Path("benchmark") / "results" / value).resolve()
    if nested.exists():
        return nested

    raise FileNotFoundError(
        f"Could not find results directory: {value}. "
        "Pass a full path or run-folder name under benchmark/results/."
    )


def _setup_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "figure.dpi": 130,
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "font.family": "DejaVu Sans",
        }
    )


def _save_fig(fig: Any, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _pair_label(row: dict[str, Any]) -> str:
    src = row.get("source_language", "")
    tgt = row.get("target_language", "")
    tts = " +TTS" if _to_bool(row.get("include_speech")) else ""
    return f"{src}->{tgt}{tts}"


def _plot_kpi_overview(summary: dict[str, Any], out_path: Path) -> None:
    totals = summary.get("totals", {})
    client = summary.get("client_latency_ms", {})
    server = summary.get("server_total_latency_ms", {})
    config = summary.get("config", {})

    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    fig.suptitle(f"Vaani Benchmark KPI Overview ({config.get('run_id', 'run')})", fontsize=16, fontweight="bold")

    cards = [
        ("Success Rate", f"{totals.get('success_rate_pct', 0)}%", "#0a9396"),
        ("Total Requests", f"{totals.get('requests', 0)}", "#005f73"),
        ("Client p95 Latency", f"{client.get('p95_ms', 'n/a')} ms", "#ee9b00"),
        ("Server p95 Latency", f"{server.get('p95_ms', 'n/a')} ms", "#ca6702"),
    ]

    for ax, (title, value, color) in zip(axes.flat, cards):
        ax.axis("off")
        ax.set_facecolor("#f7f7f7")
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=24, color=color, fontweight="bold")
        ax.text(0.5, 0.32, title, ha="center", va="center", fontsize=12, color="#333333")

    _save_fig(fig, out_path)


def _plot_latency_percentiles(summary: dict[str, Any], out_path: Path) -> None:
    client = summary.get("client_latency_ms", {})
    server = summary.get("server_total_latency_ms", {})
    labels = ["p50_ms", "p90_ms", "p95_ms", "p99_ms"]
    client_vals = [_to_float(client.get(label)) or 0.0 for label in labels]
    server_vals = [_to_float(server.get(label)) or 0.0 for label in labels]

    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar([i - 0.2 for i in x], client_vals, width=0.4, label="Client latency", color="#1d3557")
    ax.bar([i + 0.2 for i in x], server_vals, width=0.4, label="Server latency", color="#457b9d")
    ax.set_xticks(list(x), [label.replace("_ms", "").upper() for label in labels])
    ax.set_ylabel("Milliseconds")
    ax.set_title("Latency Percentiles")
    ax.legend()
    _save_fig(fig, out_path)


def _plot_pair_latency(pair_rows: list[dict[str, str]], out_path: Path) -> None:
    enriched: list[tuple[str, float]] = []
    for row in pair_rows:
        value = _to_float(row.get("client_p95_ms"))
        if value is None:
            continue
        enriched.append((_pair_label(row), value))

    enriched.sort(key=lambda item: item[1], reverse=True)
    labels = [item[0] for item in enriched]
    values = [item[1] for item in enriched]

    fig, ax = plt.subplots(figsize=(12, max(5.5, 0.45 * len(labels))))
    ax.barh(labels, values, color="#264653")
    ax.invert_yaxis()
    ax.set_xlabel("Client p95 latency (ms)")
    ax.set_title("Language Pair Latency (p95)")
    _save_fig(fig, out_path)


def _plot_pair_success(pair_rows: list[dict[str, str]], out_path: Path) -> None:
    enriched: list[tuple[str, float]] = []
    for row in pair_rows:
        value = _to_float(row.get("success_rate_pct"))
        if value is None:
            continue
        enriched.append((_pair_label(row), value))

    enriched.sort(key=lambda item: item[1])
    labels = [item[0] for item in enriched]
    values = [item[1] for item in enriched]
    colors = ["#e76f51" if v < 99 else "#2a9d8f" for v in values]

    fig, ax = plt.subplots(figsize=(12, max(5.5, 0.45 * len(labels))))
    ax.barh(labels, values, color=colors)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Success rate (%)")
    ax.set_title("Language Pair Reliability")
    _save_fig(fig, out_path)


def _plot_route_distribution(route_rows: list[dict[str, str]], out_path: Path) -> None:
    labels = [row.get("translation_route", "unknown") for row in route_rows]
    values = [_to_float(row.get("requests")) or 0.0 for row in route_rows]

    fig, ax = plt.subplots(figsize=(8, 6))
    if sum(values) <= 0:
        ax.text(0.5, 0.5, "No route data", ha="center", va="center", fontsize=14)
        ax.axis("off")
    else:
        ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90, wedgeprops={"linewidth": 1, "edgecolor": "white"})
        ax.set_title("Model Route Distribution")
    _save_fig(fig, out_path)


def _plot_error_distribution(error_rows: list[dict[str, str]], out_path: Path) -> None:
    labels = []
    values = []
    for row in error_rows:
        count = _to_float(row.get("requests")) or 0.0
        if count <= 0:
            continue
        error_type = row.get("error_type", "unknown")
        status_code = row.get("status_code") or "-"
        labels.append(f"{error_type} ({status_code})")
        values.append(count)

    fig, ax = plt.subplots(figsize=(9, 5))
    if not values:
        ax.text(0.5, 0.5, "No errors in this run", ha="center", va="center", fontsize=15, color="#2a9d8f")
        ax.axis("off")
    else:
        ax.bar(labels, values, color="#e63946")
        ax.set_ylabel("Request count")
        ax.set_title("Error Distribution")
        ax.tick_params(axis="x", rotation=20)
    _save_fig(fig, out_path)


def _plot_request_scatter(raw_rows: list[dict[str, str]], out_path: Path) -> None:
    client = []
    server = []
    for row in raw_rows:
        if not _to_bool(row.get("success")):
            continue
        x = _to_float(row.get("client_latency_ms"))
        y = _to_float(row.get("metric_total_latency_ms"))
        if x is None or y is None:
            continue
        client.append(x)
        server.append(y)

    fig, ax = plt.subplots(figsize=(7, 6))
    if not client:
        ax.text(0.5, 0.5, "No request-level latency pairs found", ha="center", va="center", fontsize=13)
        ax.axis("off")
    else:
        max_val = max(max(client), max(server))
        ax.scatter(client, server, alpha=0.65, color="#1d3557", edgecolors="white", linewidths=0.4)
        ax.plot([0, max_val], [0, max_val], linestyle="--", color="#e76f51", linewidth=1.5, label="x = y")
        ax.set_xlabel("Client latency (ms)")
        ax.set_ylabel("Server latency (ms)")
        ax.set_title("Client vs Server Latency per Request")
        ax.legend()
    _save_fig(fig, out_path)


def _plot_stage_breakdown(raw_rows: list[dict[str, str]], out_path: Path) -> None:
    stages = [
        ("Preprocess", "metric_translation_preprocess_ms_sum", "#457b9d"),
        ("Tokenize", "metric_translation_tokenize_ms_sum", "#1d3557"),
        ("Generate", "metric_translation_generate_ms_sum", "#e9c46a"),
        ("Decode", "metric_translation_decode_ms_sum", "#f4a261"),
        ("TTS", "metric_tts_latency_ms", "#2a9d8f"),
    ]

    means = []
    labels = []
    colors = []
    for label, key, color in stages:
        values = [_to_float(row.get(key)) for row in raw_rows if _to_float(row.get(key)) is not None]
        if not values:
            continue
        means.append(sum(values) / len(values))
        labels.append(label)
        colors.append(color)

    fig, ax = plt.subplots(figsize=(9, 5))
    if not means:
        ax.text(0.5, 0.5, "No stage-level timing data", ha="center", va="center", fontsize=13)
        ax.axis("off")
    else:
        ax.bar(labels, means, color=colors)
        ax.set_ylabel("Average latency (ms)")
        ax.set_title("Average Stage Latency Breakdown")
    _save_fig(fig, out_path)


def _write_index_md(out_path: Path, chart_paths: list[Path], summary: dict[str, Any]) -> None:
    totals = summary.get("totals", {})
    lines = [
        "# Presentation Graph Pack",
        "",
        f"- Run ID: `{summary.get('config', {}).get('run_id', 'unknown')}`",
        f"- Requests: `{totals.get('requests', 0)}`",
        f"- Success rate: `{totals.get('success_rate_pct', 0)}%`",
        "",
        "## Charts",
        "",
    ]
    for chart in chart_paths:
        lines.append(f"### {chart.stem}")
        lines.append(f"![{chart.stem}]({chart.name})")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render presentation-ready graphs for one benchmark run.")
    parser.add_argument(
        "result_dir_or_name",
        help="Full path to benchmark result folder OR just run folder name under benchmark/results.",
    )
    parser.add_argument(
        "--output-subdir",
        default="plots",
        help="Subdirectory inside the run folder where chart images are written (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _setup_style()

    results_dir = _resolve_results_dir(args.result_dir_or_name)
    summary_path = results_dir / "summary.json"
    pair_path = results_dir / "pair_summary.csv"
    route_path = results_dir / "route_summary.csv"
    error_path = results_dir / "error_summary.csv"
    raw_path = results_dir / "raw_requests.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Missing required file: {summary_path}")

    summary = _read_json(summary_path)
    pair_rows = _read_csv(pair_path) if pair_path.exists() else []
    route_rows = _read_csv(route_path) if route_path.exists() else []
    error_rows = _read_csv(error_path) if error_path.exists() else []
    raw_rows = _read_csv(raw_path) if raw_path.exists() else []

    plot_dir = results_dir / args.output_subdir
    plot_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = [
        plot_dir / "01_kpi_overview.png",
        plot_dir / "02_latency_percentiles.png",
        plot_dir / "03_pair_p95_latency.png",
        plot_dir / "04_pair_success_rate.png",
        plot_dir / "05_route_distribution.png",
        plot_dir / "06_error_distribution.png",
        plot_dir / "07_client_vs_server_scatter.png",
        plot_dir / "08_stage_latency_breakdown.png",
    ]

    _plot_kpi_overview(summary, chart_paths[0])
    _plot_latency_percentiles(summary, chart_paths[1])
    _plot_pair_latency(pair_rows, chart_paths[2])
    _plot_pair_success(pair_rows, chart_paths[3])
    _plot_route_distribution(route_rows, chart_paths[4])
    _plot_error_distribution(error_rows, chart_paths[5])
    _plot_request_scatter(raw_rows, chart_paths[6])
    _plot_stage_breakdown(raw_rows, chart_paths[7])

    index_md = plot_dir / "presentation_graphs.md"
    _write_index_md(index_md, chart_paths, summary)

    print(f"Rendered {len(chart_paths)} charts.")
    print(f"Output directory: {plot_dir}")
    print(f"Index markdown: {index_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
