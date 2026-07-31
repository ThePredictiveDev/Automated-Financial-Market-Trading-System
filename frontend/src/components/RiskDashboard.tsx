import React from 'react';
import type { SnapshotPayload } from '../types';
import { ShieldAlert, ShieldCheck, HelpCircle, CheckCircle2 } from 'lucide-react';

interface RiskDashboardProps {
  data: SnapshotPayload | null;
  prices: Record<string, number>;
}

const MAX_GROSS_NOTIONAL = 10_000_000;
const MAX_SYMBOL_POSITION = 50_000;
const MAX_ORDER_QTY = 5000;

export const RiskDashboard: React.FC<RiskDashboardProps> = ({ data, prices }) => {
  const positions = data?.portfolio?.positions || {};
  const netLiq = data?.portfolio?.net_liq || 1_000_000;

  // Calculate gross exposure: sum(|position_qty * price|)
  const grossExposure = Object.entries(positions).reduce((sum, [sym, qty]) => {
    const price = prices[sym] || data?.last_price || 0;
    return sum + Math.abs(qty * price);
  }, 0);

  const leverage = netLiq > 0 ? grossExposure / netLiq : 0;

  // Compile warning details
  const warnings: string[] = [];
  if (grossExposure > MAX_GROSS_NOTIONAL) {
    warnings.push(`Gross Exposure ($${grossExposure.toLocaleString()}) exceeds notional limit ($${MAX_GROSS_NOTIONAL.toLocaleString()})`);
  }
  
  Object.entries(positions).forEach(([sym, qty]) => {
    if (Math.abs(qty) > MAX_SYMBOL_POSITION) {
      warnings.push(`Position size in ${sym} (${Math.abs(qty).toLocaleString()} shs) exceeds symbol position limit (${MAX_SYMBOL_POSITION.toLocaleString()} shs)`);
    }
  });

  // Calculate limit utilization percentages
  const exposurePct = Math.min(100, (grossExposure / MAX_GROSS_NOTIONAL) * 100);
  
  // Find highest single position size utilization
  const maxPosQty = Object.values(positions).reduce((m, q) => Math.max(m, Math.abs(q)), 0);
  const posQtyPct = Math.min(100, (maxPosQty / MAX_SYMBOL_POSITION) * 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '6px' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '1px' }}>
          <ShieldAlert size={11} color="var(--accent-amber)" />
          <span style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-main)' }}>Risk Validation Dashboard</span>
        </div>
        <p style={{ fontSize: '8px', color: 'var(--text-dim)', lineHeight: 1.35 }}>
          Pre-trade validation gate. <strong>Flow Interaction:</strong> Intercepts orders between submission and order book queue. If all limits pass, dispatches a FIX MsgType=8 ACK and routes to the Matching Engine. Breaches reject immediately, halting downstream engine processes.
        </p>
      </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: '16px', flex: 1, padding: '0' }}>

      
      {/* Column 1: Risk Exposure Telemetry */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '2px', letterSpacing: '0.5px' }}>
          Exposure Telemetry
        </h4>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '2px' }}>
              <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Gross Exposure</span>
              <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
                <HelpCircle size={9} />
                <div className="tooltip-box">
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Gross Exposure</span>
                  Sum of absolute values of all open stock positions: `Σ |Qty * Price|`.
                </div>
              </span>
            </div>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: grossExposure > MAX_GROSS_NOTIONAL * 0.8 ? 'var(--sell-red)' : 'var(--text-main)' }}>
              ${grossExposure.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '2px' }}>
              <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Risk Leverage</span>
              <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
                <HelpCircle size={9} />
                <div className="tooltip-box">
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Leverage</span>
                  Ratio of gross position exposure to account equity (`Gross Exposure / Net Liquidation`).
                </div>
              </span>
            </div>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: leverage > 2.5 ? 'var(--accent-amber)' : 'var(--text-main)' }}>
              {leverage.toFixed(2)}x
            </span>
          </div>
        </div>

        {/* Progress bars showing Utilization of limits */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '2px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'var(--text-muted)', marginBottom: '2px' }}>
              <span>Notional Limit Utilization</span>
              <span className="mono">{exposurePct.toFixed(1)}% (${MAX_GROSS_NOTIONAL.toLocaleString()})</span>
            </div>
            <div style={{ height: '5px', background: 'var(--bg-dark)', borderRadius: '2px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
              <div style={{ height: '100%', width: `${exposurePct}%`, background: exposurePct > 80 ? 'var(--sell-red)' : 'var(--buy-green)', transition: 'width 0.3s' }} />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: 'var(--text-muted)', marginBottom: '2px' }}>
              <span>Max Position Utilization</span>
              <span className="mono">{posQtyPct.toFixed(1)}% ({MAX_SYMBOL_POSITION.toLocaleString()} shs)</span>
            </div>
            <div style={{ height: '5px', background: 'var(--bg-dark)', borderRadius: '2px', overflow: 'hidden', border: '1px solid var(--border-color)' }}>
              <div style={{ height: '100%', width: `${posQtyPct}%`, background: posQtyPct > 80 ? 'var(--sell-red)' : 'var(--buy-green)', transition: 'width 0.3s' }} />
            </div>
          </div>
        </div>
      </div>

      {/* Column 2: Gateway Rule Checklist */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '2px', letterSpacing: '0.5px' }}>
          Active Risk Rules
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1, overflowY: 'auto' }}>
          {/* Rule checklist */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9px', background: 'var(--bg-input)', padding: '3px 6px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <CheckCircle2 size={10} color="var(--buy-green)" />
            <span style={{ color: 'var(--text-muted)' }}>Rule #1: Owner Killed switch</span>
            <span style={{ marginLeft: 'auto', fontWeight: 700, color: 'var(--buy-green)' }}>ACTIVE</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9px', background: 'var(--bg-input)', padding: '3px 6px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <CheckCircle2 size={10} color="var(--buy-green)" />
            <span style={{ color: 'var(--text-muted)' }}>Rule #2: Symbol halts validation</span>
            <span style={{ marginLeft: 'auto', fontWeight: 700, color: 'var(--buy-green)' }}>ACTIVE</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9px', background: 'var(--bg-input)', padding: '3px 6px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <CheckCircle2 size={10} color="var(--buy-green)" />
            <span style={{ color: 'var(--text-muted)' }}>Rule #3: Max Order Qty ({MAX_ORDER_QTY})</span>
            <span style={{ marginLeft: 'auto', fontWeight: 700, color: 'var(--buy-green)' }}>ACTIVE</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9px', background: 'var(--bg-input)', padding: '3px 6px', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
            <CheckCircle2 size={10} color="var(--buy-green)" />
            <span style={{ color: 'var(--text-muted)' }}>Rule #4: Gross Exposure check</span>
            <span style={{ marginLeft: 'auto', fontWeight: 700, color: 'var(--buy-green)' }}>ACTIVE</span>
          </div>
        </div>
      </div>

      {/* Column 3: Active Warnings / Status */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '2px', letterSpacing: '0.5px' }}>
          Breaches & Alerts
        </h4>

        {warnings.length === 0 ? (
          <div style={{
            flex: 1, background: 'rgba(0, 230, 118, 0.03)', border: '1px solid rgba(0, 230, 118, 0.1)',
            borderRadius: '5px', display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', gap: '4px', color: 'var(--buy-green)', padding: '8px', textAlign: 'center'
          }}>
            <ShieldCheck size={18} />
            <span style={{ fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' }}>GATEWAY STATUS NOMINAL</span>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>All trade requests cleared</span>
          </div>
        ) : (
          <div style={{
            flex: 1, background: 'rgba(255, 23, 68, 0.04)', border: '1px solid rgba(255, 23, 68, 0.2)',
            borderRadius: '5px', padding: '6px 8px', display: 'flex', flexDirection: 'column', gap: '4px',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--sell-red)', fontWeight: 800, fontSize: '9px', marginBottom: '2px' }}>
              <ShieldAlert size={12} />
              <span>ACTIVE RISK BREACHES ({warnings.length})</span>
            </div>
            {warnings.map((warn, i) => (
              <div key={i} style={{ fontSize: '8px', color: 'var(--sell-red)', paddingLeft: '10px', position: 'relative', lineHeight: 1.3 }}>
                <span style={{ position: 'absolute', left: '2px' }}>•</span>
                {warn}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
    </div>
  );
};
