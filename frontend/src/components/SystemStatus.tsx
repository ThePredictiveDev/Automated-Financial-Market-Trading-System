import React from 'react';

interface SystemStatusProps {
  isConnected: boolean;
  tickRate: number;
  messageRate: number;
  uptimeSec: number;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({
  isConnected,
  tickRate,
  messageRate,
  uptimeSec,
}) => {
  const formatTime = (totalSeconds: number) => {
    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = Math.floor(totalSeconds % 60);
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const services = [
    { 
      name: 'Matching Engine Core', 
      status: isConnected ? 'ONLINE' : 'OFFLINE', 
      color: isConnected ? 'var(--buy-green)' : 'var(--sell-red)',
      desc: 'Runs the FIFO Double Auction execution logic for orders.'
    },
    { 
      name: 'Market Data Feed', 
      status: isConnected && tickRate > 0 ? 'ONLINE' : 'STANDBY', 
      color: isConnected && tickRate > 0 ? 'var(--buy-green)' : 'var(--accent-amber)',
      desc: 'Streams real-time pricing random-walk ticks to bots.'
    },
    { 
      name: 'Order Event Stream (WS)', 
      status: isConnected ? 'CONNECTED' : 'DISCONNECTED', 
      color: isConnected ? 'var(--buy-green)' : 'var(--sell-red)',
      desc: 'Bridges raw engine updates and trade events to client browsers.'
    },
    { 
      name: 'FIX Session Gateway', 
      status: 'SIMULATED', 
      color: 'var(--accent-amber)',
      desc: 'Handles institutional FIX (Financial Information eXchange) messaging protocol connectivity.'
    },
    { 
      name: 'Persistence Logger', 
      status: 'CSV + DB ACTIVE', 
      color: 'var(--buy-green)',
      desc: 'Journals all transaction executions and logs to local CSV files.'
    },
    { 
      name: 'Replay Engine Manager', 
      status: 'STANDBY', 
      color: 'var(--text-dim)',
      desc: 'Plays back historical events logs for regression testing strategies.'
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px', height: '100%', minHeight: 0, padding: '2px 0', overflow: 'hidden' }}>
      {/* Subsystem health status card */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minHeight: 0, overflow: 'hidden' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '2px', flexShrink: 0 }}>
          Subsystem Gateway Architecture
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px', overflowY: 'auto', minHeight: 0, flex: 1 }}>
          {services.map((srv, idx) => (
            <div key={idx} className="tooltip-trigger" style={{
              background: 'var(--bg-input)', border: '1px solid var(--border-color)',
              borderRadius: '4px', padding: '6px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>{srv.name}</span>
              <span className="mono" style={{ fontSize: '9px', fontWeight: 800, color: srv.color }}>{srv.status}</span>
              {/* Tooltip containing details */}
              <div className="tooltip-box">
                <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>{srv.name}</span>
                {srv.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Network / Diagnostic statistics */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minHeight: 0, overflow: 'hidden' }}>
        <h4 style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '2px', flexShrink: 0 }}>
          Telemetry Diagnostics
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '5px', minHeight: 0, overflowY: 'auto' }}>
          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', textAlign: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)', display: 'block' }}>Tick Frequency</span>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: 'var(--accent-cyan)' }}>
              {isConnected ? `${tickRate.toFixed(1)}/s` : '--'}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', textAlign: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)', display: 'block' }}>WS Frame Rate</span>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: 'var(--accent-cyan)' }}>
              {isConnected ? `${messageRate.toFixed(1)}/s` : '--'}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', textAlign: 'center' }}>
            <span style={{ fontSize: '8px', color: 'var(--text-dim)', display: 'block' }}>Session Uptime</span>
            <span className="mono" style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-main)' }}>
              {formatTime(uptimeSec)}
            </span>
          </div>

          <div style={{ background: 'var(--bg-input)', padding: '5px 8px', borderRadius: '4px', border: '1px solid var(--border-color)', textAlign: 'center', gridColumn: 'span 3', color: 'var(--text-dim)' }}>
            <span style={{ fontSize: '9px', lineHeight: 1.3, display: 'block' }}>
              <strong>Educational Architecture:</strong> Backend processes are running inside a single-threaded Python `asyncio` event loop driving double-auction matches, risk controls, and market feeds.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

