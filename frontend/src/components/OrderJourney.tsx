import React from 'react';
import type { LifecycleState, LifecycleStage } from '../types';
import {
  Activity, Send, ShieldCheck, CheckSquare, Layers,
  Cpu, Zap, FileSpreadsheet, TrendingUp, Database,
  Radio, BarChart4, AlertTriangle, CheckCircle2, Clock, HelpCircle
} from 'lucide-react';

interface OrderJourneyProps {
  lifecycle: LifecycleState;
}

interface JourneyStep {
  id: LifecycleStage;
  label: string;
  subsystem: string;
  educationalNote: string;
  interactionNote: string;
  icon: React.ComponentType<{ size: number; color?: string }>;
}

const JOURNEY_STEPS: JourneyStep[] = [
  {
    id: 'market_data',
    label: 'Market Data Feed',
    subsystem: 'Feed Aggregator',
    educationalNote: 'Reads current L1/L2 spread and tick history to establish the mid-market price reference.',
    interactionNote: 'Feeds live price updates to trading bots to trigger quotes and ensures user order pricing is within bounds.',
    icon: Activity,
  },
  {
    id: 'order_submit',
    label: 'Order Submission',
    subsystem: 'Order Ticket / API Client',
    educationalNote: 'Stamps a unique UUID, tracks side (Buy/Sell), type, price, and quantity, and dispatches the request.',
    interactionNote: 'Routes the raw order parameters directly to the pre-trade gateway risk manager for validation.',
    icon: Send,
  },
  {
    id: 'risk_check',
    label: 'Risk Validation',
    subsystem: 'RiskManager',
    educationalNote: 'Applies four gateway constraints: Single Order Size, Max Position Size, Max Gross Notional, and Rate Limits.',
    interactionNote: 'Acts as a strict pre-trade gate. If checks pass, forwards order; if any limit breaches, rejects and halts execution.',
    icon: ShieldCheck,
  },
  {
    id: 'order_accepted',
    label: 'Order Accepted',
    subsystem: 'Order Gateway / FIX Session',
    educationalNote: 'Receives the gateway acknowledgement (equivalent to FIX MsgType=8 New Order ACK).',
    interactionNote: 'Acknowledges receipt to the client, generates a live order state, and passes it into the order book queue.',
    icon: CheckSquare,
  },
  {
    id: 'order_book',
    label: 'Entered Order Book',
    subsystem: 'L2 Order Book',
    educationalNote: 'Enters the Level 2 order book and is queued by price-time priority.',
    interactionNote: 'Maintains bids/asks queues. Limit orders rest here until matched; market orders cross immediately.',
    icon: Layers,
  },
  {
    id: 'matching_engine',
    label: 'Matching Engine',
    subsystem: 'FIFO Matcher',
    educationalNote: 'Performs continuous double auction checking if the incoming order price crosses resting orders.',
    interactionNote: 'Executes crossing trades by price-time priority and allocates fills to counterparties.',
    icon: Cpu,
  },
  {
    id: 'trade_exec',
    label: 'Trade Execution',
    subsystem: 'Execution Desk',
    educationalNote: 'Matches counterparties and constructs standard fill records containing trade ID, price, and quantity.',
    interactionNote: 'Dispatches execution events to both the clearing desk and the event broadcast feed.',
    icon: Zap,
  },
  {
    id: 'exec_report',
    label: 'Execution Report',
    subsystem: 'Client Gateway',
    educationalNote: 'Generates and delivers a fill confirmation execution report (MsgType=8 Fill) back to the caller.',
    interactionNote: 'Updates the client dashboard with execution details and feeds the local logger.',
    icon: FileSpreadsheet,
  },
  {
    id: 'portfolio_update',
    label: 'Portfolio Updated',
    subsystem: 'Portfolio Service',
    educationalNote: 'Recalculates cash balance, symbol positions, average cost basis, and realized/unrealized P&L.',
    interactionNote: 'Updates the user portfolio state, adjusts purchasing power, and updates risk exposure metrics.',
    icon: TrendingUp,
  },
  {
    id: 'persistence',
    label: 'Persistence Logger',
    subsystem: 'Journaler (CSV/DB)',
    educationalNote: 'Asynchronously records order and trade states into local SQLite files and CSV audit logs.',
    interactionNote: 'Provides persistence for post-trade compliance, system audit logs, and historical replay.',
    icon: Database,
  },
  {
    id: 'streaming',
    label: 'Event Streaming',
    subsystem: 'WebSocket Broadcast',
    educationalNote: 'Broadcasts the updated system state and recent trades to all connected dashboard client sessions.',
    interactionNote: 'Ensures real-time synchronization between the matching engine state and client UI components.',
    icon: Radio,
  },
  {
    id: 'analytics',
    label: 'Performance Analytics',
    subsystem: 'Analytics Engine',
    educationalNote: 'Recalculates rolling Sharpe ratio, Sortino ratio, max drawdown, and session equity metrics.',
    interactionNote: 'Feeds live analytics metrics to the performance dashboard to display system efficiency.',
    icon: BarChart4,
  },
];

const STAGE_ORDER: LifecycleStage[] = [
  'idle',
  'market_data',
  'order_submit',
  'risk_check',
  'order_accepted',
  'order_book',
  'matching_engine',
  'trade_exec',
  'exec_report',
  'portfolio_update',
  'persistence',
  'streaming',
  'analytics'
];

export const OrderJourney: React.FC<OrderJourneyProps> = ({ lifecycle }) => {
  const { stage, side, price, quantity, orderType, timings, error, orderId } = lifecycle;

  const currentStageIdx = STAGE_ORDER.indexOf(stage);
  const hasOrder = stage !== 'idle';

  const getStepStatus = (step: JourneyStep, stepIdx: number): 'done' | 'active' | 'error' | 'waiting' => {
    if (!hasOrder) return 'waiting';
    const stepStageIdx = STAGE_ORDER.indexOf(step.id);
    if (error && (step.id === 'risk_check' || stepIdx > 2)) {
      if (step.id === 'risk_check') return 'error';
      return 'waiting';
    }
    if (currentStageIdx > stepStageIdx) return 'done';
    if (currentStageIdx === stepStageIdx) return 'active';
    return 'waiting';
  };

  const getTimingLabel = (step: JourneyStep, idx: number): string => {
    const tCurrent = timings[step.id];
    if (tCurrent == null) return '';

    if (idx === 0) {
      // First timing (market_data timestamp)
      return new Date(tCurrent * 1000).toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 2
      } as Intl.DateTimeFormatOptions);
    }

    // Get preceding step's time to compute delta
    const prevStepId = JOURNEY_STEPS[idx - 1]?.id;
    const tPrev = timings[prevStepId];
    if (tPrev != null) {
      const ms = ((tCurrent - tPrev) * 1000).toFixed(1);
      return `+${ms}ms`;
    }
    return '';
  };

  const statusColors = {
    done: 'var(--buy-green)',
    active: 'var(--accent-cyan)',
    error: 'var(--sell-red)',
    waiting: 'var(--text-dim)',
  };

  const statusBg = {
    done: 'rgba(0,230,118,0.04)',
    active: 'rgba(0,229,255,0.04)',
    error: 'rgba(255,23,68,0.04)',
    waiting: 'transparent',
  };

  const statusBorder = {
    done: 'rgba(0,230,118,0.2)',
    active: 'rgba(0,229,255,0.2)',
    error: 'rgba(255,23,68,0.2)',
    waiting: 'var(--border-color)',
  };

  return (
    <div className="terminal-panel" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Clock size={11} color="var(--accent-cyan)" />
          <h3 style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Current Order Journey
          </h3>
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)', cursor: 'pointer' }}>
            <HelpCircle size={9} />
            <div className="tooltip-box">
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Order Journey</span>
              Tracks every stage your order passes through in chronological order — from submission through risk, matching, and portfolio update.
            </div>
          </span>
        </div>
        <span style={{ fontSize: '8px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
          {hasOrder ? (orderId ? `#${orderId.slice(0, 8)}` : 'Processing…') : 'Awaiting order'}
        </span>
      </div>

      {/* Description */}
      <p style={{ fontSize: '8px', color: 'var(--text-dim)', marginBottom: '8px', marginTop: '-2px', lineHeight: 1.3, flexShrink: 0 }}>
        Tracks the complete lifecycle of your submitted order through the internal matching engine subsystem architecture.
      </p>

      {/* Order summary badge */}
      {hasOrder && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px',
          background: 'var(--bg-input)', border: '1px solid var(--border-color)',
          borderRadius: '4px', padding: '4px 8px', flexShrink: 0,
        }}>
          <span style={{
            fontWeight: 800, fontSize: '8px', textTransform: 'uppercase',
            color: side === 'buy' ? 'var(--buy-green)' : 'var(--sell-red)',
            background: side === 'buy' ? 'var(--buy-green-bg)' : 'var(--sell-red-bg)',
            padding: '1px 4px', borderRadius: '2px',
          }}>{side}</span>
          <span className="mono" style={{ fontSize: '10px', fontWeight: 700 }}>
            {quantity} shs @ ${price?.toFixed(2)}
          </span>
          <span style={{ fontSize: '9px', color: 'var(--text-dim)', marginLeft: 'auto', fontFamily: 'var(--font-mono)' }}>
            {orderType?.toUpperCase()} ORDER
          </span>
        </div>
      )}

      {/* Empty state */}
      {!hasOrder && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '6px', color: 'var(--text-dim)' }}>
          <Send size={18} color="var(--border-color)" />
          <span style={{ fontSize: '9px', textAlign: 'center', maxWidth: '160px', lineHeight: 1.4 }}>
            Submit an order via the order ticket to trace its progression through the backend architecture
          </span>
        </div>
      )}

      {/* Steps List */}
      {hasOrder && (
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px', minHeight: 0 }}>
          {JOURNEY_STEPS.map((step, idx) => {
            const status = getStepStatus(step, idx);
            const timingLabel = getTimingLabel(step, idx);
            const Icon = step.icon;

            return (
              <div
                key={step.id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: '6px',
                  padding: '4px 6px', borderRadius: '4px',
                  background: statusBg[status],
                  border: `1px solid ${statusBorder[status]}`,
                  transition: 'all 0.2s',
                  opacity: status === 'waiting' ? 0.3 : 1,
                }}
              >
                {/* Icon bubble */}
                <div style={{
                  width: '18px', height: '18px', borderRadius: '50%', flexShrink: 0,
                  background: status === 'waiting' ? 'var(--bg-input)' : statusBg[status],
                  border: `1px solid ${statusColors[status]}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  ...(status === 'active' ? { animation: 'journeyPulse 1.2s ease-in-out infinite' } : {}),
                }}>
                  {status === 'done'
                    ? <CheckCircle2 size={8} color="var(--buy-green)" />
                    : status === 'error'
                    ? <AlertTriangle size={8} color="var(--sell-red)" />
                    : <Icon size={8} color={statusColors[status]} />
                  }
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1px' }}>
                    <div>
                      <span style={{
                        fontSize: '9px', fontWeight: 800,
                        color: status === 'waiting' ? 'var(--text-dim)' : statusColors[status],
                      }}>
                        {step.label}
                      </span>
                      <span style={{ fontSize: '7px', color: 'var(--text-dim)', marginLeft: '6px', textTransform: 'uppercase', letterSpacing: '0.2px' }}>
                        [{step.subsystem}]
                      </span>
                    </div>
                    <span className="mono" style={{
                      fontSize: '8px',
                      color: timingLabel.startsWith('+') ? 'var(--accent-cyan)' : 'var(--text-dim)',
                      fontWeight: 600,
                    }}>
                      {status === 'active' && !timingLabel ? '…' : timingLabel}
                    </span>
                  </div>
                  
                  {/* Explanations */}
                  <p style={{ fontSize: '8px', color: 'var(--text-dim)', lineHeight: 1.2, margin: 0 }}>
                    {status === 'error' && step.id === 'risk_check'
                      ? `Reject Reason: ${error}`
                      : step.educationalNote}
                  </p>
                  
                  {status !== 'waiting' && status !== 'error' && (
                    <p style={{ fontSize: '7.5px', color: 'var(--accent-cyan)', opacity: 0.8, lineHeight: 1.2, marginTop: '2px', margin: 0 }}>
                      <span style={{ fontWeight: 700 }}>Flow Connection:</span> {step.interactionNote}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
