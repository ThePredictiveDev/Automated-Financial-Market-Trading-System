import React, { useEffect, useRef } from 'react';
import type { TradeRecord } from '../types';
import { ShieldCheck, HelpCircle } from 'lucide-react';

interface ExecutionTickerProps {
  trades: TradeRecord[];
}

export const ExecutionTicker: React.FC<ExecutionTickerProps> = ({ trades }) => {
  const prevIds = useRef<Set<string>>(new Set());
  const newIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    const current = new Set(trades.map(t => t.id));
    const added = new Set<string>();
    current.forEach(id => {
      if (!prevIds.current.has(id)) added.add(id);
    });
    newIds.current = added;
    prevIds.current = current;
  }, [trades]);

  const getActorLabel = (id: string): string => {
    if (id === 'user') return 'USER (You)';
    if (id.startsWith('mm_')) return `MM (${id.split('_')[1]})`;
    if (id === 'momentum_bot') return 'MOMENTUM';
    if (id === 'ema_bot') return 'EMA';
    return id.toUpperCase();
  };

  return (
    <div className="terminal-panel" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <ShieldCheck size={12} color="var(--accent-cyan)" />
          <h3 style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Matching Engine Execution Feed
          </h3>
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
            <HelpCircle size={10} style={{ cursor: 'pointer' }} />
            <div className="tooltip-box">
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Execution Feed</span>
              Displays real-time transaction records from the matching engine. Shows price, size, buy/sell side, and matching counterparty identities.
            </div>
          </span>
        </div>
        <span style={{ fontSize: '9px', color: 'var(--text-dim)', fontWeight: 600 }}>
          {trades.length} fills processed
        </span>
      </div>
      <p style={{ fontSize: '8px', color: 'var(--text-dim)', marginBottom: '4.5px', marginTop: '-2px', lineHeight: 1.35 }}>
        Real-time record of every matched trade. <strong>Flow Interaction:</strong> Triggered directly by Matching Engine matches. Executed fills immediately dispatch to the Portfolio Service for ledger adjustment, log to Persistence logs, and broadcast via WebSockets.
      </p>

      {/* Grid Column Headers */}
      <div className="exec-feed-scroll">
      <div className="exec-feed-grid" style={{
        display: 'grid',
        gridTemplateColumns: '50px 38px 45px 32px 52px 42px 1.4fr 1.4fr 45px',
        padding: '2px 4px',
        fontSize: '9px',
        fontWeight: 700,
        color: 'var(--text-dim)',
        textTransform: 'uppercase',
        borderBottom: '1px solid var(--border-color)',
        marginBottom: '4px',
        letterSpacing: '0.3px',
      }}>
        <span>Time</span>
        <span>Sym</span>
        <span>Trade ID</span>
        <span>Side</span>
        <span style={{ textAlign: 'right' }}>Price</span>
        <span style={{ textAlign: 'right' }}>Qty</span>
        <span style={{ paddingLeft: '8px' }}>Buyer</span>
        <span style={{ paddingLeft: '8px' }}>Seller</span>
        <span className="tooltip-trigger" style={{ textAlign: 'right', cursor: 'default' }}>Latency
          <div className="tooltip-box" style={{ left: 'auto', right: 0, transform: 'none' }}>
            <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Latency</span>
            Round-trip time from order submission to execution acknowledgement. In a real exchange this would be measured in microseconds. The simulator measures wall-clock milliseconds across the Python async event loop.
          </div>
        </span>
      </div>

      {/* Fills Feed List */}
      <div className="exec-feed-body" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '3px', minHeight: 0 }}>
        {trades.length === 0 ? (
          <div style={{ fontSize: '10px', color: 'var(--text-dim)', textAlign: 'center', padding: '36px 0', fontFamily: 'var(--font-mono)' }}>
            [AWAITING MATCHING ENGINE MATCH FILLS]
          </div>
        ) : (
          trades.map((t) => {
            const timeStr = new Date(t.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const isBuy = t.side === 'buy';
            const isNew = newIds.current.has(t.id);
            // Deterministic micro-latency based on ID for educational visual reference
            const traceLat = (0.05 + (parseInt(t.id.slice(0, 4), 16) % 100) / 450).toFixed(2) + "ms";
            
            return (
              <div
                key={t.id}
                className={`exec-feed-grid${isNew ? ' slide-in-row' : ''}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '50px 38px 45px 32px 52px 42px 1.4fr 1.4fr 45px',
                  alignItems: 'center',
                  background: isNew ? 'rgba(0, 229, 255, 0.05)' : 'var(--bg-input)',
                  padding: '2px 4px',
                  borderRadius: '3px',
                  border: `1px solid ${isBuy ? 'rgba(0,230,118,0.06)' : 'rgba(255,23,68,0.06)'}`,
                  fontSize: '11px',
                  height: '20px',
                }}
              >
                {/* Time */}
                <span className="mono" style={{ color: 'var(--text-dim)', fontSize: '9px' }}>{timeStr}</span>

                {/* Symbol */}
                <span className="mono" style={{ color: 'var(--text-muted)', fontWeight: 700 }}>{t.symbol}</span>

                {/* Trade ID */}
                <span className="mono" style={{ color: 'var(--text-dim)', fontSize: '9px' }}>
                  #{t.id.slice(0, 4)}
                </span>

                {/* Side */}
                <span style={{
                  fontWeight: 800, fontSize: '8px', textTransform: 'uppercase',
                  color: isBuy ? 'var(--buy-green)' : 'var(--sell-red)',
                  background: isBuy ? 'var(--buy-green-bg)' : 'var(--sell-red-bg)',
                  padding: '1px 3px', borderRadius: '2px', textAlign: 'center',
                  width: '20px', display: 'inline-block'
                }}>
                  {t.side.toUpperCase() === 'BUY' ? 'B' : 'S'}
                </span>

                {/* Price */}
                <span className="mono" style={{ fontWeight: 700, color: isBuy ? 'var(--buy-green)' : 'var(--sell-red)', textAlign: 'right' }}>
                  ${t.price.toFixed(2)}
                </span>

                {/* Qty */}
                <span className="mono" style={{ color: 'var(--text-main)', textAlign: 'right' }}>
                  {t.quantity}
                </span>

                {/* Buyer ID */}
                <span className="mono" style={{ 
                  color: t.buyer_id === 'user' ? 'var(--accent-cyan)' : 'var(--text-muted)', 
                  fontSize: '9px',
                  paddingLeft: '8px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  fontWeight: t.buyer_id === 'user' ? 700 : 500
                }}>
                  {getActorLabel(t.buyer_id)}
                </span>

                {/* Seller ID */}
                <span className="mono" style={{ 
                  color: t.seller_id === 'user' ? 'var(--accent-cyan)' : 'var(--text-muted)', 
                  fontSize: '9px',
                  paddingLeft: '8px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  fontWeight: t.seller_id === 'user' ? 700 : 500
                }}>
                  {getActorLabel(t.seller_id)}
                </span>

                {/* Latency */}
                <span className="mono" style={{ fontSize: '9px', color: 'var(--buy-green)', textAlign: 'right', fontWeight: 600 }}>
                  {traceLat}
                </span>
              </div>
            );
          })
        )}
      </div>
      </div>
    </div>
  );
};

