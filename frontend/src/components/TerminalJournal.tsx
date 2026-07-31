import React, { useEffect, useRef } from 'react';
import { Terminal, HelpCircle } from 'lucide-react';

interface JournalEvent {
  id: string;
  time: string;
  msg: string;
  type: string;
}

interface TerminalJournalProps {
  events: JournalEvent[];
}

export const TerminalJournal: React.FC<TerminalJournalProps> = ({ events }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Keep scrolled to top because events are unshifted (newest on top)
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [events]);

  const getStyleForType = (type: string) => {
    switch (type) {
      case 'submit': return { color: '#00E5FF', label: 'GATEWAY' };
      case 'risk': return { color: '#2979FF', label: 'RISK_MGR' };
      case 'matching': return { color: '#FFB300', label: 'MATCH_ENG' };
      case 'match': return { color: '#00E676', label: 'MATCHED' };
      case 'fill': return { color: '#00E676', label: 'EXEC_FILL' };
      case 'portfolio': return { color: '#FF5722', label: 'PORTFOLIO' };
      case 'system': return { color: '#90A4AE', label: 'SYSTEM' };
      case 'fix': return { color: '#E040FB', label: 'FIX_GTWY' };
      default: return { color: '#ECEFF1', label: 'EVENT' };
    }
  };

  // Convert user friendly messages into raw HFT system log lines
  const getRawLogLine = (evt: JournalEvent) => {
    // Format message as an HFT debug line
    if (evt.type === 'submit') {
      return `ORDER_NEW: side=SUBMIT msg="${evt.msg.split(': ')[1] || evt.msg}"`;
    }
    if (evt.type === 'risk') {
      return `VALIDATE_OK: filter=limits status=CLEARED detail="${evt.msg.split(': ')[1] || evt.msg}"`;
    }
    if (evt.type === 'match' || evt.type === 'fill') {
      return `MATCHED_FILL: action=EXECUTION_CONFIRM record="${evt.msg.split(': ')[1] || evt.msg}"`;
    }
    if (evt.type === 'portfolio') {
      return `LEDGER_UPDATE: action=ADJUST_BALANCE ledger="${evt.msg.split(': ')[1] || evt.msg}"`;
    }
    if (evt.type === 'system') {
      return `DAEMON_MSG: status=NOMINAL event="${evt.msg}"`;
    }
    
    return `LOG_EVENT: msg="${evt.msg}"`;
  };

  return (
    <div className="terminal-panel" style={{ padding: '10px 12px', flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Title / Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Terminal size={12} color="var(--accent-cyan)" />
          <h3 style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            System Architecture Event Log
          </h3>
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
            <HelpCircle size={10} style={{ cursor: 'pointer' }} />
            <div className="tooltip-box">
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>System Architecture Log</span>
              Simulates a live daemon trace of backend subsystem activities including API gateway endpoints, risk checking, matching engine auctions, and journal log writing.
            </div>
          </span>
        </div>
        <span style={{ fontSize: '8px', color: 'var(--accent-cyan)', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
          STDOUT/STDERR
        </span>
      </div>

      {/* Terminal Output */}
      <div 
        ref={containerRef}
        className="mono"
        style={{ 
          flex: 1, 
          overflowY: 'auto', 
          background: '#04070D', 
          borderRadius: '4px', 
          border: '1px solid var(--border-color)', 
          padding: '6px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          fontSize: '9px',
          lineHeight: 1.4,
          minHeight: 0
        }}
      >
        {events.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', textAlign: 'center', margin: 'auto' }}>
            [NO DECOMPRESSED EVENT STREAM LOGGED]
          </div>
        ) : (
          events.map((evt) => {
            const meta = getStyleForType(evt.type);
            const rawLine = getRawLogLine(evt);
            return (
              <div key={evt.id} style={{ display: 'flex', gap: '6px', alignItems: 'flex-start', borderBottom: '1px solid rgba(255,255,255,0.01)', paddingBottom: '2px' }}>
                {/* Timestamp */}
                <span style={{ color: 'var(--text-dim)' }}>[{evt.time}]</span>
                {/* Subsystem Name */}
                <span style={{ 
                  color: meta.color, 
                  fontWeight: 700,
                  minWidth: '55px',
                  display: 'inline-block'
                }}>
                  [{meta.label}]
                </span>
                {/* Log Msg */}
                <span style={{ color: '#ECEFF1', wordBreak: 'break-all', flex: 1 }}>
                  {rawLine}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
