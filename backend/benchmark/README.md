# Benchmark Harness

This harness benchmarks `POST /translate/text` and generates presentation-ready artifacts:

- `raw_requests.csv` (request-level data)
- `pair_summary.csv` (language-pair KPI summary)
- `route_summary.csv` (model route distribution)
- `error_summary.csv`
- `summary.json`
- `summary.md` (report-ready narrative + KPI tables)

## Prerequisites

- Backend is running at `http://localhost:8000`.
- Backend exposes `POST /translate/text`.
- Backend exposes `GET /metrics/recent`.
- If API key mode is enabled, pass `--api-key`.

## Run benchmark

From `bakcend/`:

```bash
python benchmark/run_api_benchmark.py \
  --base-url http://localhost:8000 \
  --dataset benchmark/datasets/presentation_text_cases.csv \
  --runs-per-case 5 \
  --concurrency 2 \
  --tag professional-demo
```

If API key is enabled:

```bash
python benchmark/run_api_benchmark.py \
  --api-key your_key_here
```

## Output location

Results are stored at:

`benchmark/results/<timestamp>-<tag>/`

Open `summary.md` for presentation slides and use the CSV files for charts.

## Generate presentation-ready graphs

Render graphs for one run by passing either the run folder name or full path:

```bash
python benchmark/render_presentation_graphs.py 20260310T021747Z-professional-demo
```

or

```bash
python benchmark/render_presentation_graphs.py /mnt/c/vaaniconnect9/vaani-connect/bakcend/benchmark/results/20260310T021747Z-professional-demo
```

This writes charts to:

`benchmark/results/<run-folder>/plots/`

Main files:

- `01_kpi_overview.png`
- `02_latency_percentiles.png`
- `03_pair_p95_latency.png`
- `04_pair_success_rate.png`
- `05_route_distribution.png`
- `06_error_distribution.png`
- `07_client_vs_server_scatter.png`
- `08_stage_latency_breakdown.png`
- `presentation_graphs.md` (image index for quick copy/paste into slides)

## Dataset format

CSV header:

`case_id,source_language,target_language,text,include_speech`

- `case_id`: optional (auto-generated if omitted)
- `include_speech`: optional, defaults to `false`

## Important note for larger runs

The backend keeps only recent metrics in memory (`VAANI_RECENT_METRICS_LIMIT`, default `100`).
If your benchmark sends more successful requests than that limit, some internal metrics may not join to request rows.
Increase the env var before running large benchmark rounds.

If `matplotlib` is missing in your environment:

```bash
pip install matplotlib
```
