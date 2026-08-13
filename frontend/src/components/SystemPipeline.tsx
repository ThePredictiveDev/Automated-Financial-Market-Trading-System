import React, { useRef, useEffect } from 'react';
import type { LifecycleState } from '../types';
import {
  Activity, Send, ShieldCheck, CheckSquare, Layers,
  Cpu, Zap, FileSpreadsheet, TrendingUp, Database,
  Radio, BarChart4, AlertTriangle
} from 'lucide-react';

interface SystemPipelineProps {
  lifecycle: LifecycleState;
  isConnected: boolean;
  tickRate: number;
}

interface PipelineNode {
  id: string;
  label: string;
  shortLabel: string;
  desc: string;
  tooltip: string;
  icon: React.ComponentType<{ size: number; color?: string }>;
}

const NODES: PipelineNode[] = [
  {
    id: 'market_data',
    label: 'Market Data Feed',
    shortLabel: 'Mkt Data',
    desc: 'Live price ticks',
    tooltip: 'Aggregates real-time price ticks at ~0.4s intervals. Feeds all strategies and market maker quote logic.',
    icon: Activity,
  },
  {
    id: 'order_submit',
    label: 'Order Submission',
    shortLabel: 'Submitter',
    desc: 'ID stamped & routed',
    tooltip: 'A new Order object is created with a unique UUID, side, price, quantity and TIF, then dispatched to the pre-trade risk gateway.',
    icon: Send,
  },
  {
    id: 'risk_check',
    label: 'Risk Validation',
    shortLabel: 'Risk Gate',
    desc: 'Pre-trade filters',
    tooltip: 'RiskManager runs four checks: max order qty (5,000 shares), max symbol position (50,000), max gross notional ($10M), and order rate (50/s). Rejects on breach.',
    icon: ShieldCheck,
  },
  {
    id: 'order_accepted',
    label: 'Order Accepted',
    shortLabel: 'Accepted',
    desc: 'ACK dispatched',
    tooltip: 'Once all pre-trade checks pass, the gateway sends a FIX-style acknowledgement (New Order status) and queues the order for matching.',
    icon: CheckSquare,
  },
  {
    id: 'order_book',
    label: 'Order Book (L2)',
    shortLabel: 'Order Book',
    desc: 'Price-time queue',
    tooltip: 'The Level 2 Order Book maintains a sorted list of all resting limit orders. New orders join bids (buy side) or asks (sell side) by price-time priority.',
    icon: Layers,
  },
  {
    id: 'matching_engine',
    label: 'Matching Engine',
    shortLabel: 'Matching',
    desc: 'FIFO double auction',
    tooltip: 'Continuous double auction. When an incoming order crosses the opposite best price, the engine matches orders using FIFO priority and generates execution records.',
    icon: Cpu,
  },
  {
    id: 'trade_exec',
    label: 'Trade Execution',
    shortLabel: 'Fill',
    desc: 'Match fills generated',
    tooltip: 'Creates Execution records pairing buyer and seller with exact fill quantity, price, and timestamps. Publishes to all subscribed trade listeners.',
    icon: Zap,
  },
  {
    id: 'exec_report',
    label: 'Execution Report',
    shortLabel: 'Exec Rpt',
    desc: 'FIX MsgType=8',
    tooltip: 'Issues a FIX Execution Report (MsgType=8) back to the originating gateway, confirming the fill. Simulated in this web server implementation.',
    icon: FileSpreadsheet,
  },
  {
    id: 'portfolio_update',
    label: 'Portfolio Update',
    shortLabel: 'Portfolio',
    desc: 'P&L recalculated',
    tooltip: 'Portfolio.on_execution() adjusts cash balance, position inventory, average cost basis, realized and unrealized PnL for every fill.',
    icon: TrendingUp,
  },
  {
    id: 'persistence',
    label: 'Persistence Logs',
    shortLabel: 'Persist',
    desc: 'CSV & DB journal',
    tooltip: 'Asynchronously journals all order state changes and trade executions to CSV log files and SQLite databases for audit and replay.',
    icon: Database,
  },
  {
    id: 'streaming',
    label: 'Event Streaming',
    shortLabel: 'Streaming',
    desc: 'WS broadcast',
    tooltip: 'The WebSocket connection manager broadcasts the full snapshot (order book, portfolio, trades) to all connected clients after each market tick.',
    icon: Radio,
  },
  {
    id: 'analytics',
    label: 'Performance Analytics',
    shortLabel: 'Analytics',
    desc: 'PnL & Sharpe calcs',
    tooltip: 'Client-side performance engine computes the equity curve, rolling max drawdown, Sharpe ratio, and Sortino ratio from session history.',
    icon: BarChart4,
  },
];

const STAGE_INDEX_MAP: Record<string, number> = {
  idle: -1,
  market_data: 0,
  order_submit: 1,
  risk_check: 2,
  order_accepted: 3,
  order_book: 4,
  matching_engine: 5,
  trade_exec: 6,
  exec_report: 7,
  portfolio_update: 8,
  persistence: 9,
  streaming: 10,
  analytics: 11,
};

export const SystemPipeline: React.FC<SystemPipelineProps> = ({ lifecycle, isConnected, tickRate }) => {
  const { stage, orderId, side, price, quantity, orderType, timings, error } = lifecycle;

  const activeIndex = (() => {
    if (stage === 'idle') return -1;
    if (stage === 'risk_check' && error) return 2;
    return STAGE_INDEX_MAP[stage] ?? -1;
  })();

  const prevActiveRef = useRef<number>(activeIndex);
  const nodeRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Trigger node-activate animation when activeIndex advances
  useEffect(() => {
    const prev = prevActiveRef.current;
    if (activeIndex !== prev && activeIndex >= 0) {
      const el = nodeRefs.current[activeIndex];
      if (el) {
        el.classList.remove('node-activate', 'node-error');
        void el.offsetWidth; // reflow
        el.classList.add(error ? 'node-error' : 'node-activate');
      }
    }
    prevActiveRef.current = activeIndex;
  }, [activeIndex, error]);

  const getDeltaMs = (t1?: number, t2?: number) => {
    if (t1 == null || t2 == null) return '';
    return `+${((t2 - t1) * 1000).toFixed(1)}ms`;
  };

  const getNodeSubtext = (nodeId: string, idx: number): string => {
    if (nodeId === 'market_data') {
      return isConnected && tickRate > 0 ? `${tickRate.toFixed(1)} ticks/s` : 'Standby';
    }
    if (stage === 'idle') return NODES[idx].desc;
    if (error && idx > 2) return 'Halted';

    const tCurrent = timings[nodeId];
    if (tCurrent != null) {
      if (idx > 0) {
        const prevId = NODES[idx - 1].id;
        const tPrev = timings[prevId];
        if (tPrev != null) {
          return getDeltaMs(tPrev, tCurrent);
        }
      }
      return 'Done';
    }

    if (activeIndex === idx) return 'Active…';
    return 'Waiting';
  };

  return (
    <div
      className="terminal-panel pipeline-banner"
      style={{
        padding: 'var(--pipeline-pad-y, 8px) var(--pad-x, 14px)',
        background: 'linear-gradient(180deg, #0A0E1A 0%, #05080E 100%)',
        borderBottom: '2px solid var(--border-color)',
        borderRadius: 0,
        flexShrink: 0,
        overflowX: 'auto',
        overflowY: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--pipeline-inner-gap, 6px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Radio size={12} color="var(--accent-cyan)" />
          <span style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.8px', color: 'var(--text-main)' }}>
            Live Order Execution Pipeline
          </span>
          <span className="pipeline-banner-desc" style={{ fontSize: '9px', color: 'var(--text-dim)' }}>
            — Visualizes the real-time path every order takes through the matching system
          </span>
        </div>

        {/* Order Summary Badge */}
        {orderId ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px' }}>
            <span style={{
              fontWeight: 800, color: side === 'buy' ? 'var(--buy-green)' : 'var(--sell-red)',
              background: side === 'buy' ? 'var(--buy-green-bg)' : 'var(--sell-red-bg)',
              padding: '1px 5px', borderRadius: '2px', fontSize: '8px', textTransform: 'uppercase',
            }}>{side}</span>
            <span className="mono" style={{ color: 'var(--text-main)', fontWeight: 600 }}>
              {quantity} shs @ ${price?.toFixed(2)} ({orderType})
            </span>
            <span className="mono" style={{ color: 'var(--text-dim)', fontSize: '9px' }}>#{orderId.slice(0, 6)}</span>
          </div>
        ) : (
          <span style={{ fontSize: '9px', color: 'var(--text-dim)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
            STANDBY — Submit an order to animate the flow
          </span>
        )}
      </div>

      {/* Node Flow */}
      <div className="pipeline-nodes" style={{ display: 'flex', alignItems: 'center', gap: 0, padding: '2px 0' }}>
        {NODES.map((node, idx) => {
          const NodeIcon = node.icon;
          const isMD = node.id === 'market_data';
          const isCompleted = activeIndex > idx && !error;
          const isActive = activeIndex === idx;
          const isHalted = !!error && idx > 2;

          let nodeColor = 'var(--text-dim)';
          let borderCol = 'var(--border-color)';
          let bgCol = 'var(--bg-input)';
          let extraClass = '';

          if (isMD) {
            nodeColor = isConnected ? 'var(--buy-green)' : 'var(--sell-red)';
            borderCol = nodeColor;
            bgCol = isConnected ? 'rgba(0,230,118,0.06)' : 'rgba(255,23,68,0.06)';
            extraClass = isConnected ? 'node-heartbeat' : '';
          } else if (isHalted) {
            nodeColor = 'rgba(255,23,68,0.3)';
            borderCol = 'rgba(255,23,68,0.12)';
          } else if (isCompleted) {
            nodeColor = 'var(--buy-green)';
            borderCol = 'rgba(0,230,118,0.6)';
            bgCol = 'rgba(0,230,118,0.04)';
          } else if (isActive) {
            nodeColor = error ? 'var(--sell-red)' : 'var(--accent-cyan)';
            borderCol = nodeColor;
            bgCol = error ? 'rgba(255,23,68,0.06)' : 'rgba(0,229,255,0.06)';
          }

          const subtext = getNodeSubtext(node.id, idx);
          const isWireActive = isCompleted || (isActive && !error);
          const isWireErr = !!error && idx === activeIndex;

          return (
            <React.Fragment key={node.id}>
              {/* Node */}
              <div
                className="tooltip-trigger"
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: '1 1 0px', minWidth: '44px', textAlign: 'center' }}
              >
                {/* Bubble */}
                <div
                  ref={el => { nodeRefs.current[idx] = el; }}
                  className={extraClass}
                  style={{
                    width: 'var(--pipeline-node-size, 24px)', height: 'var(--pipeline-node-size, 24px)', borderRadius: '50%',
                    background: bgCol,
                    border: `1.5px solid ${borderCol}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: nodeColor,
                    transition: 'border-color 0.3s, background 0.3s',
                    position: 'relative',
                  }}
                >
                  {isActive && error && node.id === 'risk_check'
                    ? <AlertTriangle size={11} color="var(--sell-red)" />
                    : <NodeIcon size={11} color={nodeColor} />
                  }
                  {/* Active pulsing ring */}
                  {isActive && !error && (
                    <div style={{
                      position: 'absolute', inset: '-4px', borderRadius: '50%',
                      border: `1px solid ${nodeColor}`,
                      opacity: 0.5,
                      animation: 'journeyPulse 1.2s ease-in-out infinite',
                      pointerEvents: 'none',
                    }} />
                  )}
                </div>

                {/* Label */}
                <span style={{
                  fontSize: '8px', fontWeight: 700, marginTop: '3px', display: 'block',
                  color: isActive ? (error ? 'var(--sell-red)' : 'var(--accent-cyan)')
                    : isCompleted ? 'var(--text-main)' : isHalted ? 'rgba(255,255,255,0.15)' : 'var(--text-dim)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%',
                  transition: 'color 0.3s',
                }}>
                  {node.shortLabel}
                </span>

                {/* Subtext */}
                <span className="mono pipeline-node-sub" style={{
                  fontSize: '7px', marginTop: '1px', display: 'block',
                  color: isMD && isConnected ? 'var(--buy-green)'
                    : subtext.startsWith('+') ? 'var(--accent-cyan)'
                    : subtext === 'Processing…' ? 'var(--accent-amber)'
                    : isHalted ? 'rgba(255,255,255,0.1)' : 'var(--text-dim)',
                  fontWeight: 600,
                }}>
                  {subtext}
                </span>

                {/* Tooltip */}
                <div className="tooltip-box" style={{ minWidth: '180px' }}>
                  <div style={{ fontWeight: 800, fontSize: '10px', color: 'var(--accent-cyan)', marginBottom: '4px', textTransform: 'uppercase' }}>
                    {node.label}
                  </div>
                  <div style={{ color: 'var(--text-main)', fontSize: '9px', lineHeight: 1.4 }}>
                    {node.tooltip}
                  </div>
                </div>
              </div>

              {/* Connector Wire */}
              {idx < NODES.length - 1 && (
                <div style={{
                  flex: '0 0 auto',
                  height: '2px',
                  width: '10px',
                  marginBottom: '16px',
                  borderRadius: '1px',
                  background: isWireActive
                    ? `linear-gradient(90deg, var(--buy-green), var(--accent-cyan) 60%, var(--buy-green))`
                    : isWireErr
                    ? 'rgba(255,23,68,0.3)'
                    : 'var(--border-color)',
                  backgroundSize: isWireActive ? '200% 100%' : '100% 100%',
                  animation: isActive && !error ? 'wireTravel 1.5s linear infinite' : 'none',
                  transition: 'background 0.4s',
                }} />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Error Alert Bar */}
      {error && (
        <div style={{
          marginTop: '6px', fontSize: '10px', color: 'var(--sell-red)',
          background: 'rgba(255,23,68,0.06)', borderRadius: '4px',
          padding: '4px 8px', border: '1px solid rgba(255,23,68,0.2)',
          display: 'flex', alignItems: 'center', gap: '6px',
        }}>
          <AlertTriangle size={11} />
          <span><strong>PRE-TRADE RISK REJECT:</strong> {error} — Order did not reach matching engine</span>
        </div>
      )}
    </div>
  );
};
