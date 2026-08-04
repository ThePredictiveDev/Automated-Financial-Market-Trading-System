import { useCallback, useEffect, useRef, useState } from 'react';
import { Header } from './components/Header';
import { OrderBook } from './components/OrderBook';
import { CandlestickChart } from './components/CandlestickChart';
import { OrderTicket } from './components/OrderTicket';
import { SystemPipeline } from './components/SystemPipeline';
import { OrderJourney } from './components/OrderJourney';
import { TerminalJournal } from './components/TerminalJournal';
import { PortfolioSummary } from './components/PortfolioSummary';
import { StrategyPanel } from './components/StrategyPanel';
import { ExecutionTicker } from './components/ExecutionTicker';
import { PerformanceAnalytics } from './components/PerformanceAnalytics';
import { SystemStatus } from './components/SystemStatus';
import { ReplayPanel } from './components/ReplayPanel';
import { MarketActivity } from './components/MarketActivity';
import { NBBOBar } from './components/NBBOBar';
import { SessionSummary } from './components/SessionSummary';
import type { SnapshotPayload, LifecycleState, EquityPoint, TradeRecord } from './types';
import { apiUrl, wsUrl } from './config';

type BottomTab = 'portfolio' | 'strategies' | 'analytics' | 'system' | 'activity' | 'replay';

const INITIAL_LIFECYCLE: LifecycleState = {
  stage: 'idle',
  orderId: null,
  side: null,
  price: null,
  quantity: null,
  orderType: null,
  timings: {},
  error: null,
};

export function App() {
  const [data, setData] = useState<SnapshotPayload | null>(null);
  const [activeSymbol, setActiveSymbol] = useState<string>('AAPL');
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<BottomTab>('portfolio');
  const [lifecycle, setLifecycle] = useState<LifecycleState>(INITIAL_LIFECYCLE);
  const [replayMode, setReplayMode] = useState<boolean>(false);
  const [replaySummary, setReplaySummary] = useState<any | null>(null);

  const handleReplayModeChange = useCallback((enabled: boolean) => {
    setReplayMode(enabled);
    setReplaySummary(null); // clear any stale summary when entering/exiting replay
  }, []);
  
  // Client-side analytics histories
  const [equityHistory, setEquityHistory] = useState<EquityPoint[]>([]);
  const [symbolPrices, setSymbolPrices] = useState<Record<string, number>>({});
  
  // Real-time diagnostics
  const [tickRate, setTickRate] = useState(0);
  const [messageRate, setMessageRate] = useState(0);
  const [uptimeSec, setUptimeSec] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const ticksCountRef = useRef(0);
  const messagesCountRef = useRef(0);
  const lastPriceRef = useRef<number | null>(null);

  const prevTradesCountRef = useRef(0);

  const [events, setEvents] = useState<{ id: string; time: string; msg: string; type: string }[]>(() => {
    const time = new Date().toLocaleTimeString();
    return [
      { id: 'sys1', time, msg: 'Matching Engine initialized: Continuous double auction mode', type: 'system' },
      { id: 'sys2', time, msg: 'Risk manager active: Limits set at $10,000,000 max gross notional', type: 'risk' },
      { id: 'sys3', time, msg: 'Algos initialized: Market Maker, momentum, and EMA crossover', type: 'system' },
      { id: 'sys4', time, msg: `Listening for WebSocket stream at ${wsUrl('/ws/stream')}`, type: 'system' },
    ];
  });
  const [userOrderCount, setUserOrderCount] = useState(0);

  // ── Global tooltip controller ─────────────────────────────────────────────
  // Positions .tooltip-box elements using position:fixed so they escape
  // any overflow:hidden parent and are always fully visible in the viewport.
  useEffect(() => {
    let activeBox: HTMLElement | null = null;

    const showTooltip = (trigger: Element) => {
      const box = trigger.querySelector('.tooltip-box') as HTMLElement | null;
      if (!box) return;

      // Hide any previously open tooltip first
      if (activeBox && activeBox !== box) {
        activeBox.classList.remove('tt-visible');
        activeBox = null;
      }

      const rect = trigger.getBoundingClientRect();
      const GAP = 8;
      const PADDING = 8;

      // Temporarily reveal to measure dimensions
      box.style.visibility = 'hidden';
      box.style.opacity = '0';
      box.style.top = '-9999px';
      box.style.left = '-9999px';
      box.classList.add('tt-visible');

      const bw = box.offsetWidth;
      const bh = box.offsetHeight;

      // Prefer showing above the trigger; fall back to below
      let top = rect.top - bh - GAP;
      if (top < PADDING) top = rect.bottom + GAP;

      // Horizontal: centre-align, clamp to viewport
      let left = rect.left + rect.width / 2 - bw / 2;
      if (left + bw > window.innerWidth - PADDING) left = window.innerWidth - bw - PADDING;
      if (left < PADDING) left = PADDING;

      box.style.top = `${top}px`;
      box.style.left = `${left}px`;
      box.style.visibility = '';
      box.style.opacity = '';

      activeBox = box;
    };

    const hideTooltip = (trigger: Element) => {
      const box = trigger.querySelector('.tooltip-box') as HTMLElement | null;
      if (box) box.classList.remove('tt-visible');
      if (activeBox === box) activeBox = null;
    };

    const onEnter = (e: MouseEvent) => {
      const trigger = (e.target as Element).closest('.tooltip-trigger');
      if (trigger) showTooltip(trigger);
    };

    const onLeave = (e: MouseEvent) => {
      const trigger = (e.target as Element).closest('.tooltip-trigger');
      if (trigger) hideTooltip(trigger);
    };

    document.addEventListener('mouseover', onEnter, true);
    document.addEventListener('mouseout', onLeave, true);
    return () => {
      document.removeEventListener('mouseover', onEnter, true);
      document.removeEventListener('mouseout', onLeave, true);
    };
  }, []);


  const logEvent = useCallback((msg: string, type: string) => {
    const time = new Date().toLocaleTimeString();
    const id = Math.random().toString(36).substring(2, 9);
    setEvents(prev => {
      if (prev.length > 0 && prev[0].msg === msg) return prev;
      return [{ id, time, msg, type }, ...prev].slice(0, 50);
    });
  }, []);

  const lifecycleRef = useRef(lifecycle);
  useEffect(() => {
    lifecycleRef.current = lifecycle;
  }, [lifecycle]);

  // Connection, snapshot parsing, and real-time backend lifecycle events
  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      // Choose WebSocket endpoint based on replay mode
      const wsUrlFull = replayMode 
        ? wsUrl('/ws/replay') 
        : wsUrl('/ws/stream');
      
      ws = new WebSocket(wsUrlFull);
      wsRef.current = ws;
      ws.onopen = () => {
        setIsConnected(true);
        const mode = replayMode ? 'Replay' : 'Live';
        logEvent(`${mode} Connection Established`, 'system');
      };

      ws.onmessage = (event) => {
        messagesCountRef.current++;
        try {
          const payload = JSON.parse(event.data);
          
          // 1. Handle Lifecycle events from the backend Layer
          if (payload.type === 'LIFECYCLE') {
            const ev = payload.stage;
            const now = performance.now() / 1000;
            
            if (ev === 'ORDER_SUBMITTED') {
              logEvent(payload.details, 'submit');
              setLifecycle(prev => ({
                ...prev,
                stage: 'order_submit',
                orderId: payload.order_id,
                timings: { ...prev.timings, order_submit: now }
              }));
            } 
            else if (ev === 'RISK_VALIDATION') {
              if (payload.status === 'FAILED') {
                logEvent(payload.details, 'risk');
                setLifecycle(prev => ({
                  ...prev,
                  stage: 'risk_check',
                  error: payload.details,
                  timings: { ...prev.timings, risk_check: now }
                }));
              } else {
                logEvent(payload.details, 'risk');
                setLifecycle(prev => ({
                  ...prev,
                  stage: 'risk_check',
                  timings: { ...prev.timings, risk_check: now }
                }));
              }
            }
            else if (ev === 'ORDER_ACCEPTED') {
              logEvent(payload.details, 'system');
              setLifecycle(prev => ({
                ...prev,
                stage: 'order_accepted',
                timings: { ...prev.timings, order_accepted: now }
              }));
            }
            else if (ev === 'ENTERED_ORDER_BOOK') {
              logEvent(payload.details, 'system');
              setLifecycle(prev => ({
                ...prev,
                stage: 'order_book',
                timings: { ...prev.timings, order_book: now }
              }));
            }
            else if (ev === 'ORDER_MATCHED') {
              logEvent(payload.details, 'match');
              // Automatically cascade through matching engine & trade exec stages
              setLifecycle(prev => {
                const timingsUpdate = { ...prev.timings };
                timingsUpdate['matching_engine'] = now;
                timingsUpdate['trade_exec'] = now + 0.05;
                timingsUpdate['exec_report'] = now + 0.1;
                return {
                  ...prev,
                  stage: 'exec_report',
                  timings: timingsUpdate
                };
              });
            }
            else if (ev === 'PORTFOLIO_UPDATED') {
              logEvent(payload.details, 'portfolio');
              setLifecycle(prev => {
                const timingsUpdate = { ...prev.timings };
                timingsUpdate['portfolio_update'] = now;
                // Add minor delays to progress to educational stages
                setTimeout(() => {
                  setLifecycle(p => ({
                    ...p,
                    stage: 'persistence',
                    timings: { ...p.timings, persistence: (performance.now() / 1000) }
                  }));
                }, 100);
                setTimeout(() => {
                  setLifecycle(p => ({
                    ...p,
                    stage: 'streaming',
                    timings: { ...p.timings, streaming: (performance.now() / 1000) }
                  }));
                }, 200);
                setTimeout(() => {
                  setLifecycle(p => ({
                    ...p,
                    stage: 'analytics',
                    timings: { ...p.timings, analytics: (performance.now() / 1000) }
                  }));
                }, 300);
                return {
                  ...prev,
                  stage: 'portfolio_update',
                  timings: timingsUpdate
                };
              });
            }
            return;
          }

          // 2. Handle end-of-replay summary
          if (payload.type === 'REPLAY_SUMMARY') {
            setReplaySummary(payload.data);
            logEvent('Replay finished — session summary available', 'system');
            return;
          }

          // Ignore the initial replay-connect handshake (not actionable data)
          if (payload.type === 'REPLAY_CONNECTED') {
            return;
          }

          // 3. Handle standard SNAPSHOT frames
          if (payload.type === 'SNAPSHOT') {
            setData(payload);
            
            // Detect market ticks
            if (lastPriceRef.current !== payload.last_price) {
              ticksCountRef.current++;
              lastPriceRef.current = payload.last_price;
            }

            // Keep track of current symbol prices
            setSymbolPrices(prev => ({
              ...prev,
              [payload.symbol]: payload.last_price
            }));

            // Record net liquidating equity history
            if (payload.portfolio?.net_liq) {
              setEquityHistory(prev => {
                const now = Date.now();
                const lastPoint = prev[prev.length - 1];
                if (!lastPoint || now - lastPoint.t >= 1000) {
                  const updated = [...prev, { t: now, v: payload.portfolio.net_liq }];
                  return updated.slice(-100);
                }
                return prev;
              });
            }

            // Log non-user trade execution ticker updates
            if (payload.recent_trades) {
              if (prevTradesCountRef.current === 0) {
                prevTradesCountRef.current = payload.recent_trades.length;
              } else if (prevTradesCountRef.current < payload.recent_trades.length) {
                const newTrades = payload.recent_trades.slice(prevTradesCountRef.current);
                newTrades.forEach((t: TradeRecord) => {
                  if (t.buyer_id !== 'user' && t.seller_id !== 'user') {
                    logEvent(`Trade Executed: ${t.quantity} shs ${t.symbol} @ $${t.price.toFixed(2)} (${t.buyer_id} / ${t.seller_id})`, 'fill');
                  }
                });
                prevTradesCountRef.current = payload.recent_trades.length;
              }
            }

            // Log Event: Bot Quote Updated
            if (payload.strategy_states?.market_maker || payload.strategy_states?.momentum || payload.strategy_states?.ema) {
              if (lastPriceRef.current !== payload.last_price && lastPriceRef.current !== null) {
                logEvent(`Bot Quote Updated: Algos posted quotes for ${payload.symbol} @ $${payload.last_price.toFixed(2)}`, 'bot');
              }
            }
          }
        } catch (err) {
          console.error('Error parsing WebSocket frame:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        logEvent('Connection Lost - Attempting Reconnect...', 'system');
        reconnectTimeout = setTimeout(connect, 2000);
      };

      ws.onerror = () => setIsConnected(false);
    };

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(reconnectTimeout);
    };
  }, [logEvent, replayMode]); // Reconnect when replay mode changes

  // Diagnostic tracking clock loop (Runs every 1s)
  useEffect(() => {
    const iv = setInterval(() => {
      setTickRate(ticksCountRef.current);
      setMessageRate(messagesCountRef.current);
      ticksCountRef.current = 0;
      messagesCountRef.current = 0;
      setUptimeSec(prev => prev + 1);
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  const handleSymbolChange = useCallback(async (symbol: string) => {
    setActiveSymbol(symbol);
    try {
      await fetch(apiUrl('/api/symbol'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
    } catch (err) {
      console.error('Failed to change symbol:', err);
    }
  }, []);

  const handleToggleStrategy = useCallback(async (name: string, enabled: boolean) => {
    try {
      await fetch(apiUrl('/api/strategies/toggle'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_name: name, enabled }),
      });
    } catch (err) {
      console.error('Failed to toggle strategy:', err);
    }
  }, []);

  const handleCancelOrder = useCallback(async (symbol: string, orderId: string) => {
    try {
      await fetch(apiUrl(`/api/order/${symbol}/${orderId}`), {
        method: 'DELETE',
      });
      logEvent(`Cancel Request Dispatched: Order #${orderId.slice(0, 8)}`, 'submit');
    } catch (err) {
      console.error('Failed to cancel order:', err);
    }
  }, [logEvent]);

  // Order lifecycle pipeline tracking
  const handleOrderSubmit = useCallback(async (params: {
    symbol: string;
    side: 'buy' | 'sell';
    type: 'limit' | 'market';
    price: number;
    quantity: number;
    tif: string;
  }): Promise<void> => {
    setUserOrderCount(c => c + 1);
    
    // Stage 1: market_data
    const t0 = performance.now() / 1000;
    logEvent(`Order Pipeline Initiated: Referencing Market Data Feed`, 'submit');
    setLifecycle({
      stage: 'market_data',
      orderId: null,
      side: params.side,
      price: params.price,
      quantity: params.quantity,
      orderType: params.type,
      timings: { market_data: t0 },
      error: null,
    });

    // Client-side pre-submit validations
    if (params.quantity <= 0) {
      logEvent(`Pre-Trade Risk Reject: Quantity must be positive`, 'risk');
      setLifecycle(prev => ({ ...prev, stage: 'risk_check', error: 'Quantity must be positive' }));
      return;
    }
    if (params.quantity > 5000) {
      logEvent(`Pre-Trade Risk Reject: Single order size limit (5,000 shs) breached`, 'risk');
      setLifecycle(prev => ({ ...prev, stage: 'risk_check', error: 'Single order size limit (5,000 shs) breached' }));
      return;
    }
    if (params.price <= 0) {
      logEvent(`Pre-Trade Risk Reject: Price must be positive`, 'risk');
      setLifecycle(prev => ({ ...prev, stage: 'risk_check', error: 'Price must be positive' }));
      return;
    }

    try {
      const res = await fetch(apiUrl('/api/order'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, owner_id: 'user' }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Gateway reject');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Submission error';
      logEvent(`Risk Gateway Reject: ${message}`, 'risk');
      setLifecycle(prev => ({ ...prev, stage: 'risk_check', error: message }));
    }
  }, [logEvent]);

  const lastPrice = data?.last_price ?? 0;
  const bestBid = data?.best_bid ?? null;
  const bestAsk = data?.best_ask ?? null;
  const spread = data?.spread ?? 0;
  const bids = data?.bids ?? [];
  const asks = data?.asks ?? [];
  const history = data?.history ?? [];
  const userOrders = data?.user_orders ?? [];
  const recentTrades = data?.recent_trades ?? [];
  const portfolio = data?.portfolio;
  const strategyStates = data?.strategy_states;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Header
        data={data}
        activeSymbol={activeSymbol}
        onSymbolChange={handleSymbolChange}
        isConnected={isConnected}
        replayMode={replayMode}
      />

      {/* Unified execution pipeline banner right below header */}
      <SystemPipeline 
        lifecycle={lifecycle} 
        isConnected={isConnected}
        tickRate={tickRate}
      />

      {/* Inside market quote bar — always visible, no user interaction needed */}
      <NBBOBar
        bestBid={bestBid}
        bestAsk={bestAsk}
        spread={spread}
        symbol={activeSymbol}
        isConnected={isConnected}
      />

      <main
        style={{
          flex: 1,
          padding: '12px 16px',
          display: 'grid',
          gridTemplateColumns: '260px 1fr 280px',
          gridTemplateRows: '1fr',
          gap: '12px',
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {/* Left Column: Order Book */}
        <div style={{ height: '100%', minHeight: 0 }}>
          <OrderBook
            bids={bids}
            asks={asks}
            bestBid={bestBid}
            bestAsk={bestAsk}
            spread={spread}
          />
        </div>

        {/* Middle Column: Candlestick price chart + Audit execution feed */}
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0 }}>
          <div style={{ height: '170px', flexShrink: 0 }}>
            <CandlestickChart
              history={history}
              symbol={activeSymbol}
              lastPrice={lastPrice}
              bestBid={bestBid}
              bestAsk={bestAsk}
            />
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <ExecutionTicker trades={recentTrades} />
          </div>
        </div>

        {/* Right Column: Order Entry + Order Journey tracker */}
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0 }}>
          <div style={{ height: '270px', flexShrink: 0 }}>
            <OrderTicket
              symbol={activeSymbol}
              lastPrice={lastPrice}
              onOrderSubmitted={handleOrderSubmit}
            />
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <OrderJourney lifecycle={lifecycle} />
          </div>
        </div>
      </main>

      {/* Bottom Tab Bar (Secondary Panels) */}
      <div
        style={{
          background: 'var(--bg-dark)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          borderTop: '1px solid var(--border-color)',
        }}
      >
        <div className="tab-bar">
          <button
            className={`tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`}
            onClick={() => setActiveTab('portfolio')}
          >
            Portfolio &amp; Risk
          </button>
          <button
            className={`tab-btn ${activeTab === 'strategies' ? 'active' : ''}`}
            onClick={() => setActiveTab('strategies')}
          >
            Algorithmic Trading Strategies
          </button>
          <button
            className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
            onClick={() => setActiveTab('analytics')}
          >
            Performance Analytics
          </button>
          <button
            className={`tab-btn ${activeTab === 'system' ? 'active' : ''}`}
            onClick={() => setActiveTab('system')}
          >
            System Status
          </button>
          <button
            className={`tab-btn ${activeTab === 'activity' ? 'active' : ''}`}
            onClick={() => setActiveTab('activity')}
          >
            Market Activity
          </button>
          <button
            className={`tab-btn ${activeTab === 'replay' ? 'active' : ''}`}
            onClick={() => setActiveTab('replay')}
          >
            Replay Engine
          </button>
        </div>

        {/* Fixed panel height — minHeight:0 stops flex from growing with dense tab content */}
        <div
          className="tab-content"
          style={{
            height: '250px',
            maxHeight: '250px',
            minHeight: 0,
            padding: '8px 16px',
            overflow: 'hidden',
            boxSizing: 'border-box',
          }}
        >
          {activeTab === 'portfolio' && (
            <PortfolioSummary
              portfolio={portfolio}
              userOrders={userOrders}
              activeSymbol={activeSymbol}
              onCancelOrder={handleCancelOrder}
              equityHistory={equityHistory}
              prices={symbolPrices}
            />
          )}
          {activeTab === 'strategies' && (
            <StrategyPanel
              strategyStates={strategyStates}
              onToggleStrategy={handleToggleStrategy}
            />
          )}
          {activeTab === 'analytics' && (
            <PerformanceAnalytics data={data} equityHistory={equityHistory} />
          )}
          {activeTab === 'system' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', height: '100%', minHeight: 0, overflow: 'hidden' }}>
              <SystemStatus
                isConnected={isConnected}
                tickRate={tickRate}
                messageRate={messageRate}
                uptimeSec={uptimeSec}
              />
              <TerminalJournal events={events} />
            </div>
          )}
          {activeTab === 'activity' && (
            <MarketActivity
              isConnected={isConnected}
              strategyStates={strategyStates}
              recentTrades={recentTrades}
              spread={spread}
              tickRate={tickRate}
              messageRate={messageRate}
              bids={bids}
              asks={asks}
              events={events}
              userOrderCount={userOrderCount}
            />
          )}
            {activeTab === 'replay' && (
              <ReplayPanel 
                replayMode={replayMode}
                onReplayModeChange={handleReplayModeChange}
              />
            )}
        </div>
      </div>

      {replaySummary && (
        <SessionSummary
          summary={replaySummary}
          onClose={() => setReplaySummary(null)}
        />
      )}
    </div>
  );
}

export default App;

