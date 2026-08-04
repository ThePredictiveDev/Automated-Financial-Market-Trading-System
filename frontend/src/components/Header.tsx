import React from 'react';
import { Cpu, Terminal } from 'lucide-react';
import type { SnapshotPayload } from '../types';

interface HeaderProps {
  data: SnapshotPayload | null;
  activeSymbol: string;
  onSymbolChange: (symbol: string) => void;
  isConnected: boolean;
  replayMode?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  data,
  activeSymbol,
  onSymbolChange,
  isConnected,
  replayMode = false,
}) => {
  const symbols = data?.symbols || ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'AMZN'];
  const lastPrice = data?.last_price || 0;
  const spread = data?.spread || 0;

  return (
    <header className="app-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Terminal size={18} color="var(--accent-cyan)" />
          <div>
            <h1 style={{ fontSize: '15px', fontWeight: 800, letterSpacing: '0.5px', textTransform: 'uppercase' }}>
              TRADE<span style={{ color: 'var(--accent-cyan)' }}>FLOW</span>
            </h1>
            <span style={{ fontSize: '10px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginTop: '-2px' }}>
              L3 Matching Console
            </span>
          </div>
        </div>
        
        {/* LIVE/REPLAY Mode Indicator */}
        <div style={{
          padding: '4px 12px',
          borderRadius: '4px',
          background: replayMode ? 'rgba(255, 149, 0, 0.15)' : 'rgba(0, 230, 118, 0.15)',
          border: `1px solid ${replayMode ? 'var(--replay-orange)' : 'var(--buy-green)'}`,
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          <div style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: replayMode ? 'var(--replay-orange)' : 'var(--buy-green)',
            ...(replayMode ? {} : { animation: 'pulse 2s ease-in-out infinite' })
          }} />
          <span style={{
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.5px',
            textTransform: 'uppercase',
            color: replayMode ? 'var(--replay-orange)' : 'var(--buy-green)'
          }}>
            {replayMode ? 'Replay Mode' : 'Live'}
          </span>
        </div>

        {/* Symbol Selector Dropdown */}
        <div style={{ marginLeft: '16px' }}>
          <select
            value={activeSymbol}
            onChange={(e) => onSymbolChange(e.target.value)}
            className="input-field mono"
            style={{
              width: '100px',
              fontWeight: 700,
              fontSize: '13px',
              padding: '4px 24px 4px 8px',
              height: '30px',
              borderColor: 'var(--border-color)',
            }}
          >
            {symbols.map((sym) => (
              <option key={sym} value={sym}>
                {sym}
              </option>
            ))}
          </select>
        </div>

        {/* Price & Stats Header Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px', marginLeft: '8px' }}>
          <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '20px' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
              Last Trade
            </div>
            <div className="mono" style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)' }}>
              ${lastPrice.toFixed(2)}
            </div>
          </div>

          <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '20px' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
              Spread
            </div>
            <div className="mono" style={{ fontSize: '15px', fontWeight: 700, color: 'var(--accent-cyan)' }}>
              ${spread.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* System Status Indicators */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'var(--bg-dark)',
            padding: '5px 10px',
            borderRadius: '4px',
            border: '1px solid var(--border-color)',
            fontSize: '11px',
            fontWeight: 600,
            color: 'var(--text-muted)',
          }}
        >
          <Cpu size={12} color="var(--accent-cyan)" />
          <span>MATCHING ENGINE: ONLINE</span>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'var(--bg-dark)',
            padding: '5px 10px',
            borderRadius: '4px',
            border: '1px solid var(--border-color)',
            color: isConnected ? 'var(--buy-green)' : 'var(--sell-red)',
            fontSize: '11px',
            fontWeight: 700,
          }}
        >
          {isConnected && <div className="pulsing-dot" />}
          <span>{isConnected ? 'STREAM CONNECTED' : 'DISCONNECTED'}</span>
        </div>
      </div>
    </header>
  );
};
