import React from 'react';
import type { PortfolioData, UserOrder } from '../types';
import { Trash2, HelpCircle, ShieldCheck, ShieldAlert } from 'lucide-react';

interface PortfolioSummaryProps {
  portfolio: PortfolioData | undefined;
  userOrders: UserOrder[];
  activeSymbol: string;
  onCancelOrder: (symbol: string, orderId: string) => void;
  equityHistory: { t: number; v: number }[];
  prices: Record<string, number>;
}

const INITIAL_CAPITAL = 1_000_000.0;
const MAX_GROSS_NOTIONAL = 10_000_000;
const MAX_SYMBOL_POSITION = 50_000;

function MetricCard({
  label,
  value,
  color,
  tip,
}: {
  label: string;
  value: string;
  color?: string;
  tip?: string;
}) {
  return (
    <div
      style={{
        background: 'var(--bg-input)',
        padding: '4px 7px',
        borderRadius: '4px',
        border: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
        <span style={{ fontSize: '8px', color: 'var(--text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {label}
        </span>
        {tip && (
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)', flexShrink: 0 }}>
            <HelpCircle size={8} />
            <div className="tooltip-box">{tip}</div>
          </span>
        )}
      </div>
      <span
        className="mono"
        style={{ fontSize: '11px', fontWeight: 700, color: color || 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
      >
        {value}
      </span>
    </div>
  );
}

function UtilBar({ label, pct, limit }: { label: string; pct: number; limit: string }) {
  const color = pct > 80 ? 'var(--sell-red)' : pct > 50 ? 'var(--accent-amber)' : 'var(--buy-green)';
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'var(--text-dim)', marginBottom: '2px' }}>
        <span>{label}</span>
        <span className="mono" style={{ color }}>
          {pct.toFixed(1)}% / {limit}
        </span>
      </div>
      <div style={{ height: '4px', background: 'var(--bg-dark)', borderRadius: '2px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
        <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, background: color, transition: 'width 0.3s' }} />
      </div>
    </div>
  );
}

export const PortfolioSummary: React.FC<PortfolioSummaryProps> = ({
  portfolio,
  userOrders,
  activeSymbol,
  onCancelOrder,
  prices,
}) => {
  const cash = portfolio?.cash ?? 0;
  const netLiq = portfolio?.net_liq ?? 0;
  const realizedPnl = portfolio?.realized_pnl ?? 0;
  const positions = portfolio?.positions ?? {};

  // Derived P&L
  const totalReturn = netLiq - INITIAL_CAPITAL;
  const unrealizedPnl = totalReturn - realizedPnl;

  // Risk metrics — same formulas as the former standalone RiskDashboard
  const posEntries = Object.entries(positions).filter(([, qty]) => qty !== 0);
  const grossExposure = posEntries.reduce((sum, [sym, qty]) => {
    return sum + Math.abs(qty * (prices[sym] ?? 0));
  }, 0);
  const leverage = netLiq > 0 ? grossExposure / netLiq : 0;
  const maxPosQty = posEntries.reduce((m, [, q]) => Math.max(m, Math.abs(q)), 0);
  const maxPosValue = posEntries.reduce((m, [sym, q]) => Math.max(m, Math.abs(q * (prices[sym] ?? 0))), 0);
  const exposurePct = Math.min(100, (grossExposure / MAX_GROSS_NOTIONAL) * 100);
  const posQtyPct = Math.min(100, (maxPosQty / MAX_SYMBOL_POSITION) * 100);

  const warnings: string[] = [];
  if (grossExposure > MAX_GROSS_NOTIONAL * 0.8)
    warnings.push(`Gross Exposure (${grossExposure.toLocaleString(undefined, { maximumFractionDigits: 0 })}) nearing $10M limit`);
  posEntries.forEach(([sym, qty]) => {
    if (Math.abs(qty) > MAX_SYMBOL_POSITION * 0.8)
      warnings.push(`${sym} position (${Math.abs(qty).toLocaleString()} shs) nearing 50K limit`);
  });

  const pnlColor = (v: number) => (v >= 0 ? 'var(--buy-green)' : 'var(--sell-red)');

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '12px', height: '100%', minHeight: 0, overflow: 'hidden' }}>

      {/* ── Left: Portfolio Summary + Risk Summary ─────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minHeight: 0, overflow: 'hidden' }}>

        {/* Portfolio Summary */}
        <span style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', flexShrink: 0 }}>
          Account Summary
        </span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px', flexShrink: 0 }}>
          <MetricCard
            label="Net Liquidation"
            value={`$${netLiq.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            color="var(--accent-cyan)"
            tip="Cash + market value of all open positions."
          />
          <MetricCard
            label="Buying Power"
            value={`$${cash.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            color="var(--buy-green)"
            tip="Cash available. Equals Available Cash — no margin in this simulator."
          />
          <MetricCard
            label="Realized PnL"
            value={`${realizedPnl >= 0 ? '+' : ''}$${realizedPnl.toFixed(2)}`}
            color={pnlColor(realizedPnl)}
            tip="Locked-in profit/loss from completed trades."
          />
          <MetricCard
            label="Unrealized PnL"
            value={`${unrealizedPnl >= 0 ? '+' : ''}$${unrealizedPnl.toFixed(2)}`}
            color={pnlColor(unrealizedPnl)}
            tip="Floating P&L on open positions. Derived as Net Liq − $1M initial − Realized PnL."
          />
          <MetricCard
            label="Open Positions"
            value={`${posEntries.length}`}
            tip="Symbols with a non-zero position."
          />
          <MetricCard
            label="Resting Orders"
            value={`${userOrders.length}`}
            tip="Your limit orders currently sitting in the order book."
          />
        </div>

        {/* Risk Summary */}
        <span style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', flexShrink: 0, marginTop: '2px' }}>
          Risk Summary
        </span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px', flexShrink: 0 }}>
          <MetricCard
            label="Gross Exposure"
            value={`$${grossExposure.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
            color={grossExposure > MAX_GROSS_NOTIONAL * 0.8 ? 'var(--sell-red)' : 'var(--text-main)'}
            tip="Σ |qty × price| across all positions."
          />
          <MetricCard
            label="Leverage"
            value={`${leverage.toFixed(2)}x`}
            color={leverage > 2 ? 'var(--accent-amber)' : 'var(--text-main)'}
            tip="Gross Exposure ÷ Net Liquidation."
          />
          <MetricCard
            label="Largest Position"
            value={maxPosValue > 0 ? `$${maxPosValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
            tip="Market value of the single largest open position."
          />
          <MetricCard
            label="Max Pos Size"
            value={maxPosQty > 0 ? `${maxPosQty.toLocaleString()} shs` : '—'}
            tip="Largest single-symbol share count across open positions."
          />
        </div>

        {/* Utilization bars */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
          <UtilBar label="Notional Limit" pct={exposurePct} limit="$10M" />
          <UtilBar label="Position Limit" pct={posQtyPct} limit="50K shs" />
        </div>

        {/* Risk status */}
        <div
          style={{
            flexShrink: 0,
            borderRadius: '4px',
            border: warnings.length ? '1px solid rgba(255,23,68,0.3)' : '1px solid rgba(0,230,118,0.15)',
            background: warnings.length ? 'rgba(255,23,68,0.04)' : 'rgba(0,230,118,0.03)',
            padding: '4px 8px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '6px',
          }}
        >
          {warnings.length === 0 ? (
            <>
              <ShieldCheck size={11} color="var(--buy-green)" style={{ flexShrink: 0, marginTop: '1px' }} />
              <span style={{ fontSize: '9px', color: 'var(--buy-green)', fontWeight: 700 }}>NORMAL — All limits within bounds</span>
            </>
          ) : (
            <>
              <ShieldAlert size={11} color="var(--sell-red)" style={{ flexShrink: 0, marginTop: '1px' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <span style={{ fontSize: '9px', color: 'var(--sell-red)', fontWeight: 700 }}>WARNING — {warnings.length} breach{warnings.length > 1 ? 'es' : ''}</span>
                {warnings.map((w, i) => (
                  <span key={i} style={{ fontSize: '8px', color: 'var(--sell-red)', lineHeight: 1.3 }}>• {w}</span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── Right: Positions + Orders ──────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', minHeight: 0, overflow: 'hidden' }}>

        {/* Positions table */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
          <span style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', flexShrink: 0, marginBottom: '4px' }}>
            Open Positions
          </span>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', background: 'var(--bg-input)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10px' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-color)', textAlign: 'left', position: 'sticky', top: 0 }}>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px' }}>SYMBOL</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'right' }}>POSITION</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'right' }}>MKT VALUE</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'right' }}>PRICE</th>
                </tr>
              </thead>
              <tbody>
                {posEntries.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ padding: '10px 8px', color: 'var(--text-dim)', textAlign: 'center', fontSize: '10px' }}>
                      No open positions
                    </td>
                  </tr>
                ) : (
                  posEntries.map(([sym, qty]) => {
                    const price = prices[sym] ?? 0;
                    const value = qty * price;
                    return (
                      <tr key={sym} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                        <td style={{ padding: '4px 8px', fontWeight: 700 }}>{sym}</td>
                        <td className="mono" style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700, color: qty >= 0 ? 'var(--buy-green)' : 'var(--sell-red)' }}>
                          {qty > 0 ? `+${qty}` : qty}
                        </td>
                        <td className="mono" style={{ padding: '4px 8px', textAlign: 'right', color: value >= 0 ? 'var(--buy-green)' : 'var(--sell-red)' }}>
                          ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="mono" style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--text-dim)' }}>
                          ${price.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Resting orders table */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
          <span style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', flexShrink: 0, marginBottom: '4px' }}>
            Resting Orders — {activeSymbol}
          </span>
          <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', background: 'var(--bg-input)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10px' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-color)', textAlign: 'left', position: 'sticky', top: 0 }}>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px' }}>SIDE</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'right' }}>QTY</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'right' }}>PRICE</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px' }}>TYPE</th>
                  <th style={{ padding: '4px 8px', color: 'var(--text-dim)', fontWeight: 600, fontSize: '9px', textAlign: 'center' }}>✕</th>
                </tr>
              </thead>
              <tbody>
                {userOrders.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ padding: '10px 8px', color: 'var(--text-dim)', textAlign: 'center', fontSize: '10px' }}>
                      No resting orders
                    </td>
                  </tr>
                ) : (
                  userOrders.map((ord) => (
                    <tr key={ord.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                      <td style={{ padding: '4px 8px', fontWeight: 800, color: ord.side === 'buy' ? 'var(--buy-green)' : 'var(--sell-red)', textTransform: 'uppercase', fontSize: '10px' }}>
                        {ord.side}
                      </td>
                      <td className="mono" style={{ padding: '4px 8px', textAlign: 'right' }}>{ord.quantity}</td>
                      <td className="mono" style={{ padding: '4px 8px', textAlign: 'right' }}>${ord.price.toFixed(2)}</td>
                      <td className="mono" style={{ padding: '4px 8px', color: 'var(--text-dim)', fontSize: '9px', textTransform: 'uppercase' }}>
                        {ord.type}/{ord.tif}
                      </td>
                      <td style={{ padding: '2px 8px', textAlign: 'center' }}>
                        <button
                          style={{ padding: '2px 5px', background: 'rgba(255,23,68,0.08)', border: '1px solid rgba(255,23,68,0.2)', borderRadius: '3px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '3px', color: 'var(--sell-red)', fontSize: '8px', fontWeight: 700 }}
                          onClick={() => onCancelOrder(ord.symbol, ord.id)}
                        >
                          <Trash2 size={9} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
