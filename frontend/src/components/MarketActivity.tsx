import React from 'react';
import { Server, FileText } from 'lucide-react';
import type { DepthLevel, StrategyStates } from '../types';

interface MarketActivityProps {
  isConnected: boolean;
  strategyStates: StrategyStates | undefined;
  recentTrades: any[];
  spread: number;
  tickRate: number;
  messageRate: number;
  bids: DepthLevel[];
  asks: DepthLevel[];
  events: { id: string; time: string; msg: string; type: string }[];
  userOrderCount: number;
}

export const MarketActivity: React.FC<MarketActivityProps> = ({
  isConnected,
  strategyStates,
  recentTrades,
  spread,
  tickRate,
  messageRate,
  bids,
  asks,
  events,
  userOrderCount,
}) => {
  // Count user fills in the session
  const userFillsCount = recentTrades.filter(
    t => t.buyer_id === 'user' || t.seller_id === 'user'
  ).length;

  // Active algos count
  const activeBots = Object.entries(strategyStates || {})
    .filter(([_, enabled]) => enabled)
    .map(([name]) => name.replace(/_SYMBOL/g, '').toUpperCase());
  const botCount = activeBots.length;

  // Total bids and asks in the L3 book
  const totalBookDepth = bids.length + asks.length;

  // Helper to color-code event type badges
  const getBadgeStyle = (type: string) => {
    switch (type) {
      case 'submit': return { color: 'var(--accent-cyan)', border: '1px solid rgba(6,182,212,0.3)', bg: 'rgba(6,182,212,0.05)' };
      case 'risk': return { color: 'var(--accent-blue)', border: '1px solid rgba(59,130,246,0.3)', bg: 'rgba(59,130,246,0.05)' };
      case 'match': return { color: 'var(--buy-green)', border: '1px solid rgba(16,185,129,0.3)', bg: 'rgba(16,185,129,0.05)' };
      case 'fill': return { color: 'var(--buy-green)', border: '1px solid rgba(16,185,129,0.3)', bg: 'rgba(16,185,129,0.05)' };
      case 'portfolio': return { color: 'var(--accent-amber)', border: '1px solid rgba(245,158,11,0.3)', bg: 'rgba(245,158,11,0.05)' };
      case 'bot': return { color: 'var(--text-dim)', border: '1px solid rgba(100,116,139,0.2)', bg: 'rgba(100,116,139,0.02)' };
      default: return { color: 'var(--text-muted)', border: '1px solid var(--border-color)', bg: 'var(--bg-dark)' };
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: '12px', height: '100%', minHeight: 0, padding: '2px 0', overflow: 'hidden' }}>
      
      {/* Left Part: Engine Diagnostic Metrics Grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', height: '100%', minHeight: 0, overflow: 'hidden' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <Server size={12} color="var(--accent-cyan)" />
          Engine Diagnostic Metrics
        </h4>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px', flex: 1, minHeight: 0, overflowY: 'auto' }}>
          {/* Engine Status */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Engine Status</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: isConnected ? 'var(--buy-green)' : 'var(--sell-red)' }}>
              {isConnected ? 'CONNECTED' : 'OFFLINE'}
            </span>
          </div>

          {/* Market State */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Market State</span>
            <span className="mono" style={{ fontSize: '10px', fontWeight: 800, color: isConnected ? 'var(--accent-cyan)' : 'var(--text-dim)' }}>
              {isConnected ? 'CONTINUOUS' : 'DISCONNECTED'}
            </span>
          </div>

          {/* Active Algos */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Active Algos</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: botCount > 0 ? 'var(--buy-green)' : 'var(--text-muted)' }}>
              {botCount} RUNNING
            </span>
          </div>

          {/* Current Spread */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Current Spread</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: isConnected ? 'var(--accent-cyan)' : 'var(--text-dim)' }}>
              {isConnected ? `$${spread.toFixed(2)}` : '--'}
            </span>
          </div>

          {/* Orders Submitted */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Orders Submitted</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800 }}>
              {userOrderCount}
            </span>
          </div>

          {/* Orders Matched */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Orders Matched</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: userFillsCount > 0 ? 'var(--buy-green)' : 'var(--text-main)' }}>
              {userFillsCount}
            </span>
          </div>

          {/* Engine Fills */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Engine Fills</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800, color: 'var(--accent-amber)' }}>
              {recentTrades.length}
            </span>
          </div>

          {/* Book Depth */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Book Levels</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800 }}>
              {totalBookDepth} L3
            </span>
          </div>

          {/* Engine Tick Rate */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>Engine Tick Rate</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800 }}>
              {tickRate.toFixed(1)}/s
            </span>
          </div>

          {/* WS Messages rate */}
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)' }}>WS Msg Rate</span>
            <span className="mono" style={{ fontSize: '11px', fontWeight: 800 }}>
              {messageRate.toFixed(1)}/s
            </span>
          </div>
        </div>
      </div>

      {/* Right Part: Recent Engine Events Feed */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', height: '100%', minHeight: 0, overflow: 'hidden' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '2px', display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          <FileText size={12} color="var(--accent-cyan)" />
          Recent Engine Events
        </h4>

        <div style={{
          flex: 1,
          overflowY: 'auto',
          background: 'var(--bg-dark)',
          borderRadius: '5px',
          border: '1px solid var(--border-color)',
          padding: '8px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}>
          {events.length === 0 ? (
            <span style={{ fontSize: '10px', color: 'var(--text-dim)', margin: 'auto' }}>No events recorded</span>
          ) : (
            events.map((evt) => {
              const badge = getBadgeStyle(evt.type);
              return (
                <div key={evt.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', borderBottom: '1px solid rgba(255,255,255,0.01)', paddingBottom: '3px' }}>
                  <span className="mono" style={{ color: 'var(--text-dim)', fontSize: '9px' }}>[{evt.time}]</span>
                  <span className="mono" style={{
                    color: badge.color,
                    border: badge.border,
                    background: badge.bg,
                    padding: '1px 4px',
                    borderRadius: '3px',
                    fontSize: '8px',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    minWidth: '54px',
                    textAlign: 'center',
                  }}>
                    {evt.type}
                  </span>
                  <span className="mono" style={{ color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                    {evt.msg}
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
