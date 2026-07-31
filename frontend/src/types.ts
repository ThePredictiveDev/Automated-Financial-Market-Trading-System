export interface DepthLevel {
  price: number;
  quantity: number;
}

export interface HistoryPoint {
  timestamp: number;
  price: number;
  bid: number;
  ask: number;
  volume: number;
}
export interface CandleData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  bid: number;
  ask: number;
}

export interface UserOrder {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  type: 'limit' | 'market';
  price: number;
  quantity: number;
  tif: string;
}

export interface TradeRecord {
  id: string;
  symbol: string;
  price: number;
  quantity: number;
  side: string;
  buyer_id: string;
  seller_id: string;
  timestamp: number;
}

export interface PortfolioData {
  cash: number;
  realized_pnl: number;
  net_liq: number;
  positions: Record<string, number>;
}

export interface StrategyStates {
  market_maker: boolean;
  momentum: boolean;
  ema: boolean;
  swing: boolean;
  twap: boolean;
}

export interface SnapshotPayload {
  type: 'SNAPSHOT';
  symbol: string;
  symbols: string[];
  last_price: number;
  best_bid: number | null;
  best_ask: number | null;
  spread: number;
  bids: DepthLevel[];
  asks: DepthLevel[];
  history: HistoryPoint[];
  user_orders: UserOrder[];
  recent_trades: TradeRecord[];
  portfolio: PortfolioData;
  strategy_states: StrategyStates;
}

export type LifecycleStage =
  | 'idle'
  | 'market_data'
  | 'order_submit'
  | 'risk_check'
  | 'order_accepted'
  | 'order_book'
  | 'matching_engine'
  | 'trade_exec'
  | 'exec_report'
  | 'portfolio_update'
  | 'persistence'
  | 'streaming'
  | 'analytics';

export interface LifecycleState {
  stage: LifecycleStage;
  orderId: string | null;
  side: 'buy' | 'sell' | null;
  price: number | null;
  quantity: number | null;
  orderType: string | null;
  timings: Record<string, number>;
  error: string | null;
}

export interface EquityPoint {
  t: number;
  v: number;
}
