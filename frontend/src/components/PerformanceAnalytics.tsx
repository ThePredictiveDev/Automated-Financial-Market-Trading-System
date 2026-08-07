import React, { useMemo } from 'react';
import type { SnapshotPayload } from '../types';

interface PerformanceAnalyticsProps {
  data: SnapshotPayload | null;
  equityHistory: { t: number; v: number }[];
}

const INITIAL_CAPITAL = 1_000_000.0;

export const PerformanceAnalytics: React.FC<PerformanceAnalyticsProps> = ({ data, equityHistory }) => {
  const netLiq = data?.portfolio?.net_liq || INITIAL_CAPITAL;
  const totalPnl = netLiq - INITIAL_CAPITAL;

  // Calculate simple Sharpe / Sortino from client-side equity log
  const sessionMetrics = useMemo(() => {
    if (equityHistory.length < 10) {
      return { sharpe: null, sortino: null, maxDrawdown: null };
    }

    const returns: number[] = [];
    for (let i = 1; i < equityHistory.length; i++) {
      const prev = equityHistory[i - 1].v;
      const curr = equityHistory[i].v;
      if (prev > 0) {
        returns.push((curr - prev) / prev);
      }
    }

    if (returns.length === 0) {
      return { sharpe: 0, sortino: 0, maxDrawdown: 0 };
    }

    const avg = returns.reduce((a, b) => a + b, 0) / returns.length;
    const stDev = Math.sqrt(returns.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / returns.length);
    
    const negativeReturns = returns.filter(r => r < 0);
    const downsideDev = negativeReturns.length > 0 
      ? Math.sqrt(negativeReturns.reduce((a, b) => a + Math.pow(b, 2), 0) / negativeReturns.length)
      : 0;

    // Session Sharpe (non-annualized raw return standard deviation ratio)
    const sharpe = stDev > 0 ? avg / stDev : 0;
    const sortino = downsideDev > 0 ? avg / downsideDev : 0;

    // Max Drawdown calculation
    let maxDrawdown = 0;
    let peak = -Infinity;
    for (const point of equityHistory) {
      if (point.v > peak) peak = point.v;
      const dd = peak > 0 ? (peak - point.v) / peak : 0;
      if (dd > maxDrawdown) maxDrawdown = dd;
    }

    return { sharpe, sortino, maxDrawdown };
  }, [equityHistory]);

  // Mini equity curve path
  const miniChartPath = useMemo(() => {
    if (equityHistory.length < 2) return '';
    const W = 200;
    const H = 40;
    const values = equityHistory.map(h => h.v);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal || 1;

    return values.map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - minVal) / range) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }, [equityHistory]);

  const pnlColor = totalPnl >= 0 ? 'var(--buy-green)' : 'var(--sell-red)';

  return (
    <div className="analytics-layout">
      {/* Equity Line chart */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Session Equity Curve
        </h4>
        
        <div style={{ background: 'var(--bg-input)', border: '1px solid var(--border-color)', borderRadius: '5px', padding: '10px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, justifyContent: 'center' }}>
          {equityHistory.length >= 2 && miniChartPath ? (
            <svg viewBox="0 0 200 40" style={{ width: '100%', height: '40px', overflow: 'visible' }}>
              <polyline
                fill="none"
                stroke={totalPnl >= 0 ? 'var(--buy-green)' : 'var(--sell-red)'}
                strokeWidth="1.5"
                points={miniChartPath}
              />
            </svg>
          ) : (
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', textAlign: 'center', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              Accumulating session curve...
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-dim)' }}>
            <span>Start: $1M</span>
            <span>Current: ${(netLiq / 1000).toFixed(1)}k</span>
          </div>
        </div>
      </div>

      {/* Metrics breakdown */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Performance Metrics
        </h4>

        {/* 5 real metrics — Realized PnL lives in Portfolio & Risk to avoid duplication */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Total Net Return</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700, color: pnlColor }}>
              {totalPnl >= 0 ? '+' : ''}{((totalPnl / INITIAL_CAPITAL) * 100).toFixed(3)}%
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Total PnL</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700, color: pnlColor }}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Max Drawdown</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700 }}>
              {sessionMetrics.maxDrawdown !== null ? `${(sessionMetrics.maxDrawdown * 100).toFixed(2)}%` : '—'}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Sharpe Ratio</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700 }}>
              {sessionMetrics.sharpe !== null ? sessionMetrics.sharpe.toFixed(3) : 'Need 10+ pts'}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Sortino Ratio</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700 }}>
              {sessionMetrics.sortino !== null ? sessionMetrics.sortino.toFixed(3) : 'Need 10+ pts'}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', display: 'block' }}>Data Points</span>
            <span className="mono" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-dim)' }}>
              {Math.max(0, (data?.history?.length ?? 0))} ticks
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
