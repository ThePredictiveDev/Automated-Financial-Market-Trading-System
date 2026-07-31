import React, { useState } from 'react';
import { Play, Square, Info, TrendingUp, Activity, BarChart2, Layers, Brain, Clock, Code2, BookOpen } from 'lucide-react';
import type { StrategyStates } from '../types';

interface StrategyPanelProps {
  strategyStates: StrategyStates | undefined;
  onToggleStrategy: (name: string, enabled: boolean) => void;
}

type StatusType = 'live' | 'implemented' | 'utility' | 'template';

interface StrategyDef {
  key: string;
  name: string;
  sourceFile: string;
  className: string;
  status: StatusType;
  toggleKey?: string; // present only for backend-wired strategies
  icon: React.ComponentType<{ size: number; color?: string }>;
  purpose: string;
  philosophy: string;
  howItWorks: string;
  whenItTrades: string;
  params: { label: string; value: string; tooltip: string }[];
}

const STRATEGIES: StrategyDef[] = [
  {
    key: 'market_maker',
    name: 'Avellaneda-Stoikov Market Maker',
    sourceFile: 'marketmaker/market_maker.py',
    className: 'MarketMaker',
    status: 'live',
    toggleKey: 'market_maker',
    icon: Layers,
    purpose: 'Provides continuous two-sided liquidity to the order book, profiting from the bid-ask spread.',
    philosophy: 'Based on the Avellaneda-Stoikov (2008) stochastic control model. A market maker profits by quoting both sides and managing inventory risk so neither side grows too large.',
    howItWorks: 'Calculates reservation price based on inventory skew and gamma risk-aversion. Posts multi-level laddered quotes (num_levels) at intervals calculated from volatility. A drawdown kill-switch disables quoting if losses exceed the capital_base limit.',
    whenItTrades: 'Quotes are refreshed on every market data tick. The bot widens spreads when inventory is heavy, and skews quotes directionally to reduce exposure back toward zero.',
    params: [
      { label: 'gamma', value: '0.1', tooltip: 'Risk aversion coefficient. Higher = spreads skew more aggressively to reduce inventory.' },
      { label: 'k', value: '1.5', tooltip: 'Order arrival intensity. Controls how quote prices relate to the reservation price.' },
      { label: 'num_levels', value: '2', tooltip: 'Number of laddered price levels posted on each side of the book.' },
      { label: 'base_order_size', value: '100', tooltip: 'Size of each child limit order placed at each level.' },
      { label: 'drawdown_limit', value: '20%', tooltip: 'Kill-switch threshold. Quoting stops if PnL drawdown exceeds this fraction of capital_base.' },
    ],
  },
  {
    key: 'momentum',
    name: 'Momentum Trader',
    sourceFile: 'strategies/momentum.py',
    className: 'MomentumTrader',
    status: 'live',
    toggleKey: 'momentum',
    icon: TrendingUp,
    purpose: 'Captures short-term price trends by trading in the direction of recent price movement.',
    philosophy: 'Momentum trading assumes price trends persist over short horizons. By buying on up-moves and selling on down-moves, the strategy profits from trend continuation.',
    howItWorks: 'Maintains a rolling price buffer of the last `lookback` ticks. When the most recent price is higher than the oldest in the window, it submits a limit buy at best_ask. When lower, it submits a limit sell at best_bid.',
    whenItTrades: 'Every `interval` seconds, if enough history exists. Trades on any non-zero price change across the lookback window — even a small drift triggers a directional clip.',
    params: [
      { label: 'lookback', value: '5', tooltip: 'Number of price history ticks to calculate momentum over.' },
      { label: 'interval', value: '0.1s', tooltip: 'Trading cycle frequency in seconds.' },
      { label: 'risk_fraction', value: '1%', tooltip: 'Fraction of portfolio equity used to size each order when quantity is not fixed.' },
    ],
  },
  {
    key: 'ema',
    name: 'EMA Crossover Trader',
    sourceFile: 'strategies/ema.py',
    className: 'EMABasedTrader',
    status: 'live',
    toggleKey: 'ema',
    icon: Activity,
    purpose: 'Follows medium-term price trends using exponential moving average crossover signals.',
    philosophy: 'EMA crossovers are a classic technical analysis signal. When a shorter-period EMA rises above a longer one, the trend is bullish; the opposite indicates a bear trend.',
    howItWorks: 'Maintains a rolling price buffer up to long_window length. Calculates two EMAs using exponential weights (np.convolve). When short_ema > long_ema, buys at best_ask. When short_ema < long_ema, sells at best_bid.',
    whenItTrades: 'Every `interval` seconds once at least `long_window` prices have accumulated. Only fires when the cross direction changes — not on every tick.',
    params: [
      { label: 'short_window', value: '5', tooltip: 'Number of ticks for the fast (reactive) EMA.' },
      { label: 'long_window', value: '20', tooltip: 'Number of ticks for the slow (baseline) EMA. Must be > short_window.' },
      { label: 'interval', value: '0.1s', tooltip: 'Trading cycle frequency in seconds.' },
    ],
  },
  {
    key: 'swing',
    name: 'Swing Trader (Mean Reversion)',
    sourceFile: 'strategies/swing.py',
    className: 'SwingTrader',
    status: 'live',
    toggleKey: 'swing',
    icon: BarChart2,
    purpose: 'Exploits price oscillations by buying near support and resistance levels.',
    philosophy: 'Mean reversion assumes prices tend to revert toward a fair value range. When price reaches an extreme (support/resistance), the strategy bets on reversal.',
    howItWorks: 'Monitors current_price against user-defined support_level and resistance_level. If price ≤ support, buys at best_ask. If price ≥ resistance, sells at best_bid. Simple price-band trigger with no cooldown.',
    whenItTrades: 'On every `interval` tick when price touches either boundary. Requires pre-set static support and resistance levels — not adaptive to current market conditions.',
    params: [
      { label: 'support_level', value: '~94% of base', tooltip: 'Price floor. Bot buys when market price at or below this level. Dynamically set per symbol.' },
      { label: 'resistance_level', value: '~106% of base', tooltip: 'Price ceiling. Bot sells when market price at or above this level. Dynamically set per symbol.' },
      { label: 'interval', value: '0.5s', tooltip: 'Trading cycle frequency in seconds.' },
    ],
  },
  {
    key: 'twap',
    name: 'TWAP Execution Algorithm',
    sourceFile: 'strategies/twap.py',
    className: 'TWAPTrader',
    status: 'live',
    toggleKey: 'twap',
    icon: Clock,
    purpose: 'Slices a large parent order into equal-sized child clips spaced evenly over time to minimize market impact.',
    philosophy: 'Time-Weighted Average Price (TWAP) execution minimizes market impact by spreading a large order uniformly across a time window. Instead of submitting one large clip that moves the price, TWAP submits many smaller clips at fixed intervals.',
    howItWorks: 'On start, generates an execution schedule using twap_schedule() that divides the parent order (500 shares) into 5 equal slices. Tracks elapsed time and submits each child order at its scheduled offset (0s, 2.5s, 5s, 7.5s, 10s). Each child routes through risk validation → order book → matching engine.',
    whenItTrades: 'Submits child orders at fixed 2.5-second intervals over a 10-second window. Once all 5 slices are submitted, the strategy self-completes and stops trading until manually reset or re-enabled.',
    params: [
      { label: 'total_quantity', value: '500', tooltip: 'Parent order size to slice across the execution window.' },
      { label: 'num_slices', value: '5', tooltip: 'Number of equal child orders. Remainder shares distributed to early slices.' },
      { label: 'duration_seconds', value: '10.0', tooltip: 'Total execution window. Child orders spaced evenly: 10s / 5 = 2.5s intervals.' },
      { label: 'side', value: 'buy', tooltip: 'Direction of the parent order. All child orders inherit this side.' },
      { label: 'interval', value: '0.5s', tooltip: 'Polling frequency. Must be < duration/num_slices to avoid missing schedule slots.' },
    ],
  },
];

const STATUS_META: Record<StatusType, { label: string; color: string; bg: string; border: string; description: string }> = {
  live: {
    label: 'Live',
    color: 'var(--buy-green)',
    bg: 'rgba(0,230,118,0.08)',
    border: 'rgba(0,230,118,0.3)',
    description: 'Fully wired to backend — toggleable from this UI',
  },
  implemented: {
    label: 'Implemented — Not Live',
    color: 'var(--accent-amber)',
    bg: 'rgba(255,179,0,0.07)',
    border: 'rgba(255,179,0,0.25)',
    description: 'Full backend code exists but not connected to the web toggle endpoint',
  },
  utility: {
    label: 'Backend Utility',
    color: '#2979FF',
    bg: 'rgba(41,121,255,0.07)',
    border: 'rgba(41,121,255,0.25)',
    description: 'Execution helper — produces order schedules for a backtest loop or scheduler, not self-triggering',
  },
  template: {
    label: 'Developer Template',
    color: 'var(--text-muted)',
    bg: 'rgba(144,164,174,0.05)',
    border: 'rgba(144,164,174,0.2)',
    description: 'Skeleton strategy — demonstrates the required interface for building custom algorithmic traders',
  },
};

export const StrategyPanel: React.FC<StrategyPanelProps> = ({ strategyStates, onToggleStrategy }) => {
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggleExpand = (key: string) => {
    setExpanded(prev => (prev === key ? null : key));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', height: '100%', overflow: 'hidden' }}>
      {/* Intro Note */}
      <div style={{
        background: 'rgba(0,229,255,0.04)',
        border: '1px solid rgba(0,229,255,0.12)',
        borderRadius: '4px',
        padding: '6px 10px',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
          <BookOpen size={11} color="var(--accent-cyan)" style={{ marginTop: '1px', flexShrink: 0 }} />
          <p style={{ fontSize: '9px', color: 'var(--text-muted)', lineHeight: 1.4 }}>
            These strategies demonstrate different approaches to interacting with the same matching engine and are
            included to showcase the breadth of the trading system architecture. Each uses the shared{' '}
            <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>AlgorithmicTrader</span>{' '}
            base class and routes all orders through the same pre-trade risk gateway, order book, and FIFO matching engine.
          </p>
        </div>
      </div>

      {/* Status Legend */}
      <div style={{
        display: 'flex', gap: '8px', flexWrap: 'wrap', flexShrink: 0,
        background: 'var(--bg-input)', border: '1px solid var(--border-color)',
        borderRadius: '4px', padding: '5px 8px', alignItems: 'center',
      }}>
        <span style={{ fontSize: '8px', color: 'var(--text-dim)', fontWeight: 700, textTransform: 'uppercase', marginRight: '2px' }}>Legend:</span>
        {(Object.entries(STATUS_META) as [StatusType, typeof STATUS_META[StatusType]][]).map(([key, meta]) => (
          <span key={key} className="tooltip-trigger" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', cursor: 'default' }}>
            <span style={{
              width: '6px', height: '6px', borderRadius: '50%', background: meta.color, flexShrink: 0,
            }} />
            <span style={{ fontSize: '8px', color: 'var(--text-muted)', fontWeight: 600 }}>{meta.label}</span>
            <div className="tooltip-box">
              <span style={{ color: meta.color, fontWeight: 800, display: 'block', marginBottom: '2px' }}>{meta.label}</span>
              {meta.description}
            </div>
          </span>
        ))}
      </div>

      {/* Strategy Cards Grid */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '6px', alignContent: 'start', minHeight: 0 }}>
        {STRATEGIES.map((strat) => {
          const meta = STATUS_META[strat.status];
          const isLive = strat.status === 'live';
          const isOn = isLive && strat.toggleKey ? (strategyStates?.[strat.toggleKey as keyof StrategyStates] ?? false) : false;
          const isExpanded = expanded === strat.key;
          const Icon = strat.icon;

          return (
            <div
              key={strat.key}
              style={{
                background: 'var(--bg-input)',
                border: `1px solid ${isExpanded ? meta.border : 'var(--border-color)'}`,
                borderRadius: '5px',
                padding: '8px 10px',
                display: 'flex',
                flexDirection: 'column',
                gap: '5px',
                transition: 'border-color 0.2s',
              }}
            >
              {/* Card Header */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flex: 1, minWidth: 0 }}>
                  <div style={{
                    width: '22px', height: '22px', borderRadius: '4px', flexShrink: 0,
                    background: meta.bg, border: `1px solid ${meta.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon size={11} color={meta.color} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '9px', fontWeight: 800, color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {strat.name}
                    </div>
                    <div style={{ fontSize: '8px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      {strat.sourceFile}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                  {/* Status Badge */}
                  <span style={{
                    fontSize: '7px', fontWeight: 800, textTransform: 'uppercase',
                    color: meta.color, background: meta.bg,
                    padding: '1px 4px', borderRadius: '2px', border: `1px solid ${meta.border}`,
                    whiteSpace: 'nowrap',
                  }}>
                    ● {meta.label}
                  </span>

                  {/* Toggle button (live strategies only) */}
                  {isLive && strat.toggleKey && (
                    <button
                      className={`btn ${isOn ? 'btn-buy' : 'btn-outline'}`}
                      style={{ padding: '1px 6px', fontSize: '8px', height: '18px', gap: '3px' }}
                      onClick={() => onToggleStrategy(strat.toggleKey!, !isOn)}
                    >
                      {isOn ? <Square size={7} /> : <Play size={7} />}
                      {isOn ? 'Active' : 'Enable Strategy'}
                    </button>
                  )}

                  {/* Expand toggle */}
                  <button
                    style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      color: 'var(--text-dim)', padding: '2px',
                      display: 'flex', alignItems: 'center',
                    }}
                    onClick={() => toggleExpand(strat.key)}
                    title={isExpanded ? 'Collapse' : 'Expand details'}
                  >
                    <Info size={10} color={isExpanded ? 'var(--accent-cyan)' : 'var(--text-dim)'} />
                  </button>
                </div>
              </div>

              {/* Purpose (always visible) */}
              <p style={{ fontSize: '8px', color: 'var(--text-muted)', lineHeight: 1.35, margin: 0 }}>
                <strong>Purpose:</strong> {strat.purpose}
              </p>

              {/* Expanded Detail */}
              {isExpanded && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: '2px' }}>
                  <div>
                    <div style={{ fontSize: '8px', fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: '2px' }}>Trading Philosophy</div>
                    <p style={{ fontSize: '8px', color: 'var(--text-muted)', lineHeight: 1.35, margin: 0 }}>{strat.philosophy}</p>
                  </div>
                  <div>
                    <div style={{ fontSize: '8px', fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: '2px' }}>How It Works</div>
                    <p style={{ fontSize: '8px', color: 'var(--text-muted)', lineHeight: 1.35, margin: 0 }}>{strat.howItWorks}</p>
                  </div>
                  <div>
                    <div style={{ fontSize: '8px', fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: '2px' }}>When It Trades</div>
                    <p style={{ fontSize: '8px', color: 'var(--text-muted)', lineHeight: 1.35, margin: 0 }}>{strat.whenItTrades}</p>
                  </div>
                  <div>
                    <div style={{ fontSize: '8px', fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: '3px' }}>Key Parameters</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px' }}>
                      {strat.params.map(p => (
                        <span key={p.label} className="tooltip-trigger mono" style={{
                          fontSize: '8px', color: 'var(--text-dim)',
                          border: '1px solid var(--border-color)',
                          padding: '1px 5px', borderRadius: '3px',
                          cursor: 'default', background: 'var(--bg-dark)',
                        }}>
                          {p.label}={p.value}
                          <div className="tooltip-box">
                            <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>{p.label}</span>
                            {p.tooltip}
                          </div>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
