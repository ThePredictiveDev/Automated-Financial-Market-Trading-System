"""Performance metrics (Sharpe, Sortino, CAGR, max drawdown) and a
self-contained HTML report."""
from __future__ import annotations

import os
from typing import Dict

import numpy as np
import pandas as pd


def load_equity_curve(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Equity curve file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns or "net_liquidation" not in df.columns:
        raise RuntimeError("Equity CSV missing required columns (timestamp, net_liquidation)")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def compute_performance_metrics(equity_df: pd.DataFrame) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    if equity_df.empty:
        return metrics
    series = equity_df.set_index("timestamp")["net_liquidation"].astype(float)
    initial, final = float(series.iloc[0]), float(series.iloc[-1])
    metrics["initial"], metrics["final"] = initial, final

    daily = series.resample("1D").last().dropna()
    if len(daily) >= 2:
        returns = daily.pct_change().dropna()
        if not returns.empty:
            mean, std = float(returns.mean()), float(returns.std(ddof=0))
            downside = returns[returns < 0]
            downside_std = float(downside.std(ddof=0)) if not downside.empty else 0.0
            metrics["sharpe"] = (mean / std * np.sqrt(252.0)) if std > 0 else 0.0
            metrics["sortino"] = (mean / downside_std * np.sqrt(252.0)) if downside_std > 0 else 0.0
        num_days = (daily.index[-1] - daily.index[0]).days or 1
        years = num_days / 365.25
        metrics["cagr"] = (final / initial) ** (1.0 / years) - 1.0 if initial > 0 and years > 0 else 0.0
        roll_max = daily.cummax()
        metrics["max_drawdown"] = float((daily / roll_max - 1.0).min())
    else:
        metrics.update({"sharpe": 0.0, "sortino": 0.0, "cagr": 0.0, "max_drawdown": 0.0})
    return metrics


def export_html_report(equity_df: pd.DataFrame, metrics: Dict[str, float], output_path: str) -> None:
    labels = [ts.isoformat() for ts in equity_df["timestamp"]]
    values = [float(v) for v in equity_df["net_liquidation"]]
    rows = "".join(f"<tr><td>{k}</td><td>{v:.6f}</td></tr>" for k, v in metrics.items())
    html = f"""<!doctype html>
<html><head>
<meta charset="utf-8"/><title>Performance Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: Arial, sans-serif; margin: 24px; }}
  .row {{ display: flex; gap: 24px; }} .col {{ flex: 1; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 6px; }} th {{ background: #f2f2f2; }}
</style></head>
<body>
  <h2>Performance Report</h2>
  <div class="row">
    <div class="col"><h3>Equity Curve</h3><canvas id="eq"></canvas></div>
    <div class="col"><h3>Metrics</h3><table><thead><tr><th>Metric</th><th>Value</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
  </div>
  <script>
    const labels = {labels};
    const data = {values};
    new Chart(document.getElementById('eq').getContext('2d'), {{
      type: 'line',
      data: {{ labels, datasets: [{{ label: 'Net Liq', data, borderColor: '#1976d2', fill: false }}] }},
      options: {{ responsive: true, scales: {{ x: {{ display: false }} }} }}
    }});
  </script>
</body></html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
