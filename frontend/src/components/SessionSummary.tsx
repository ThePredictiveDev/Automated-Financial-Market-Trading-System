import React from 'react';
import { TrendingUp, DollarSign, Activity, Clock, Target, BarChart3 } from 'lucide-react';

interface SessionSummaryData {
  duration: number;
  user_orders: number;
  executions: number;
  total_volume: number;
  average_spread: number;
  active_strategies: string[];
  final_pnl: number;
  event_count: number;
}

interface SessionSummaryProps {
  summary: SessionSummaryData;
  onClose: () => void;
}

export const SessionSummary: React.FC<SessionSummaryProps> = ({ summary, onClose }) => {
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };
  
  const formatCurrency = (value: number) => {
    return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.85)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      backdropFilter: 'blur(8px)'
    }}>
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '24px',
        maxWidth: '600px',
        width: '90%',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BarChart3 size={20} color="var(--accent-cyan)" />
            Session Summary
          </h2>
          <button onClick={onClose} className="btn btn-secondary" style={{ fontSize: '11px', padding: '6px 12px' }}>
            Close
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          {/* Duration */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Clock size={16} color="var(--accent-cyan)" />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                Duration
              </span>
            </div>
            <div className="mono" style={{ fontSize: '24px', fontWeight: 700 }}>
              {formatDuration(summary.duration)}
            </div>
          </div>

          {/* User Orders */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Target size={16} color="var(--accent-cyan)" />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                User Orders
              </span>
            </div>
            <div className="mono" style={{ fontSize: '24px', fontWeight: 700 }}>
              {summary.user_orders}
            </div>
          </div>

          {/* Executions */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Activity size={16} color="var(--buy-green)" />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                Executions
              </span>
            </div>
            <div className="mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--buy-green)' }}>
              {summary.executions}
            </div>
          </div>

          {/* Total Volume */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <DollarSign size={16} color="var(--accent-amber)" />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                Total Volume
              </span>
            </div>
            <div className="mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-amber)' }}>
              {formatCurrency(summary.total_volume)}
            </div>
          </div>

          {/* Average Spread */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <BarChart3 size={16} color="var(--text-muted)" />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                Avg Spread
              </span>
            </div>
            <div className="mono" style={{ fontSize: '20px', fontWeight: 700 }}>
              ${summary.average_spread.toFixed(3)}
            </div>
          </div>

          {/* Final P&L */}
          <div className="terminal-panel" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <TrendingUp size={16} color={summary.final_pnl >= 0 ? 'var(--buy-green)' : 'var(--sell-red)'} />
              <span style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
                Final P&L
              </span>
            </div>
            <div className="mono" style={{ fontSize: '20px', fontWeight: 700, color: summary.final_pnl >= 0 ? 'var(--buy-green)' : 'var(--sell-red)' }}>
              {formatCurrency(summary.final_pnl)}
            </div>
          </div>
        </div>

        {/* Active Strategies */}
        <div className="terminal-panel" style={{ padding: '16px', marginTop: '16px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '8px' }}>
            Active Strategies ({summary.active_strategies.length})
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {summary.active_strategies.map((strategy, idx) => (
              <span key={idx} style={{
                padding: '4px 10px',
                background: 'var(--accent-cyan-bg)',
                border: '1px solid var(--accent-cyan)',
                borderRadius: '4px',
                fontSize: '10px',
                fontWeight: 600,
                textTransform: 'uppercase',
                color: 'var(--accent-cyan)'
              }}>
                {strategy}
              </span>
            ))}
            {summary.active_strategies.length === 0 && (
              <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>None</span>
            )}
          </div>
        </div>

        {/* Event Count */}
        <div style={{ marginTop: '16px', padding: '12px', background: 'var(--bg-input)', borderRadius: '4px', textAlign: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
            Total Events Recorded: <span className="mono" style={{ fontWeight: 600, color: 'var(--text-main)' }}>{summary.event_count.toLocaleString()}</span>
          </span>
        </div>
      </div>
    </div>
  );
};
