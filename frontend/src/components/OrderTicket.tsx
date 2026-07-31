import React, { useState, useEffect } from 'react';
import { Send, ArrowUpRight, ArrowDownRight, HelpCircle } from 'lucide-react';

interface OrderTicketProps {
  symbol: string;
  lastPrice: number;
  onOrderSubmitted: (params: {
    symbol: string;
    side: 'buy' | 'sell';
    type: 'limit' | 'market';
    price: number;
    quantity: number;
    tif: string;
  }) => Promise<void>;
}

const MAX_ORDER_QTY = 5000;
const MAX_GROSS_NOTIONAL = 10_000_000;

export const OrderTicket: React.FC<OrderTicketProps> = ({
  symbol,
  lastPrice,
  onOrderSubmitted,
}) => {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [orderType, setOrderType] = useState<'limit' | 'market'>('limit');
  const [price, setPrice] = useState<string>(lastPrice ? lastPrice.toFixed(2) : '100.00');
  const [quantity, setQuantity] = useState<number>(100);
  const [tif, setTif] = useState<'GTC' | 'IOC' | 'FOK'>('GTC');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (lastPrice) {
      setPrice(lastPrice.toFixed(2));
    }
  }, [symbol]);

  const currentPriceValue = orderType === 'limit' ? parseFloat(price) || lastPrice : lastPrice;
  const estimatedValue = currentPriceValue * quantity;

  // Pre-trade checks
  const isQtyBreached = quantity > MAX_ORDER_QTY;
  const isNotionalBreached = estimatedValue > MAX_GROSS_NOTIONAL;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    // Block submission if client-side validation catches it
    if (isQtyBreached) {
      setErrorMsg(`Quantity exceeds pre-trade risk limit of ${MAX_ORDER_QTY.toLocaleString()} shs.`);
      return;
    }
    if (isNotionalBreached) {
      setErrorMsg(`Notional value exceeds limit of $${MAX_GROSS_NOTIONAL.toLocaleString()}.`);
      return;
    }

    setIsSubmitting(true);
    try {
      await onOrderSubmitted({
        symbol,
        side,
        type: orderType,
        price: orderType === 'limit' ? parseFloat(price) || lastPrice : lastPrice,
        quantity: Number(quantity),
        tif,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Submission error';
      setErrorMsg(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectJoinPrice = (type: 'bid' | 'ask') => {
    if (lastPrice) {
      const offset = type === 'bid' ? -0.01 : 0.01;
      setPrice((lastPrice + offset).toFixed(2));
    }
  };

  return (
    <div className="terminal-panel" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Title Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', borderBottom: '1px solid var(--border-color)', paddingBottom: '4px' }}>
        <h3 style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Order Entry Ticket
        </h3>
        <span className="mono" style={{ fontSize: '11px', color: 'var(--accent-cyan)', fontWeight: 800 }}>
          {symbol}
        </span>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, justifyContent: 'space-between' }}>
        {/* Buy / Sell Buttons */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <button
            type="button"
            className="btn"
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              height: '26px',
              background: side === 'buy' ? 'var(--buy-green)' : 'var(--bg-input)',
              color: side === 'buy' ? '#000' : 'var(--text-muted)',
              border: `1px solid ${side === 'buy' ? 'var(--buy-green)' : 'var(--border-color)'}`,
            }}
            onClick={() => setSide('buy')}
            disabled={isSubmitting}
          >
            <ArrowUpRight size={12} /> BUY
          </button>

          <button
            type="button"
            className="btn"
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              height: '26px',
              background: side === 'sell' ? 'var(--sell-red)' : 'var(--bg-input)',
              color: side === 'sell' ? '#fff' : 'var(--text-muted)',
              border: `1px solid ${side === 'sell' ? 'var(--sell-red)' : 'var(--border-color)'}`,
            }}
            onClick={() => setSide('sell')}
            disabled={isSubmitting}
          >
            <ArrowDownRight size={12} /> SELL
          </button>
        </div>

        {/* Order Type & TIF */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '2px' }}>
              <label style={{ fontSize: '9px', color: 'var(--text-muted)' }}>Order Type</label>
              <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
                <HelpCircle size={9} style={{ cursor: 'pointer' }} />
                <div className="tooltip-box">
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Order Type</span>
                  <strong>Limit</strong>: execute at specified price or better.<br />
                  <strong>Market</strong>: execute immediately at current best available book price.
                </div>
              </span>
            </div>
            <select
              className="input-field"
              value={orderType}
              onChange={(e) => setOrderType(e.target.value as 'limit' | 'market')}
              style={{ height: '24px', padding: '2px 6px', fontSize: '11px' }}
            >
              <option value="limit">Limit</option>
              <option value="market">Market</option>
            </select>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '2px' }}>
              <label style={{ fontSize: '9px', color: 'var(--text-muted)' }}>Time In Force</label>
              <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
                <HelpCircle size={9} style={{ cursor: 'pointer' }} />
                <div className="tooltip-box">
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Time In Force (TIF)</span>
                  <strong>GTC</strong>: Good-Til-Cancelled (remains working on book).<br />
                  <strong>IOC</strong>: Immediate-Or-Cancel (fills immediately, cancels remainder).<br />
                  <strong>FOK</strong>: Fill-Or-Kill (fills entirely immediately or cancels).
                </div>
              </span>
            </div>
            <select
              className="input-field"
              value={tif}
              onChange={(e) => setTif(e.target.value as 'GTC' | 'IOC' | 'FOK')}
              style={{ height: '24px', padding: '2px 6px', fontSize: '11px' }}
            >
              <option value="GTC">GTC</option>
              <option value="IOC">IOC</option>
              <option value="FOK">FOK</option>
            </select>
          </div>
        </div>

        {/* Price & Quantity */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <div>
            <label style={{ fontSize: '9px', color: 'var(--text-muted)', display: 'block', marginBottom: '2px' }}>
              {orderType === 'limit' ? 'Price ($)' : 'Market Price'}
            </label>
            <input
              type="text"
              className="input-field mono"
              value={orderType === 'limit' ? price : 'MKT'}
              disabled={orderType === 'market'}
              onChange={(e) => setPrice(e.target.value)}
              style={{
                height: '24px',
                padding: '2px 6px',
                background: orderType === 'market' ? 'var(--bg-dark)' : 'var(--bg-input)',
                color: orderType === 'market' ? 'var(--text-dim)' : 'var(--text-main)',
                fontSize: '11px',
              }}
              required
            />
            {/* Quick Price offsets */}
            {orderType === 'limit' && (
              <div style={{ display: 'flex', gap: '4px', marginTop: '3px' }}>
                <button type="button" onClick={() => selectJoinPrice('bid')} style={{ fontSize: '8px', padding: '1px 3px', border: '1px solid var(--border-color)', background: 'transparent', cursor: 'pointer', color: 'var(--buy-green)' }}>Join Bid</button>
                <button type="button" onClick={() => selectJoinPrice('ask')} style={{ fontSize: '8px', padding: '1px 3px', border: '1px solid var(--border-color)', background: 'transparent', cursor: 'pointer', color: 'var(--sell-red)' }}>Join Ask</button>
              </div>
            )}
          </div>

          <div>
            <label style={{ fontSize: '9px', color: 'var(--text-muted)', display: 'block', marginBottom: '2px' }}>
              Quantity (shs)
            </label>
            <input
              type="number"
              step="1"
              min="1"
              max={MAX_ORDER_QTY}
              className="input-field mono"
              value={quantity}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === '') {
                  setQuantity(1);
                  return;
                }
                const n = parseInt(raw, 10);
                if (Number.isNaN(n)) return;
                setQuantity(Math.max(1, n));
              }}
              style={{
                height: '24px',
                padding: '2px 6px',
                fontSize: '11px',
                borderColor: isQtyBreached ? 'var(--sell-red)' : 'var(--border-color)',
              }}
              required
            />
            {/* Quick size selectors */}
            <div style={{ display: 'flex', gap: '4px', marginTop: '3px' }}>
              <button type="button" onClick={() => setQuantity(100)} style={{ fontSize: '8px', padding: '1px 3px', border: '1px solid var(--border-color)', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)' }}>100</button>
              <button type="button" onClick={() => setQuantity(1000)} style={{ fontSize: '8px', padding: '1px 3px', border: '1px solid var(--border-color)', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)' }}>1k</button>
              <button type="button" onClick={() => setQuantity(5000)} style={{ fontSize: '8px', padding: '1px 3px', border: '1px solid var(--border-color)', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)' }}>5k</button>
            </div>
          </div>
        </div>

        {/* Estimated Value & Submit Action */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
          {/* Risk warning alerts */}
          {isQtyBreached && (
            <div style={{ color: 'var(--sell-red)', fontSize: '8px', fontWeight: 600, display: 'flex', gap: '2px' }}>
              ⚠️ Exceeds Gateway Risk Qty Limit (max {MAX_ORDER_QTY})
            </div>
          )}
          {isNotionalBreached && (
            <div style={{ color: 'var(--sell-red)', fontSize: '8px', fontWeight: 600, display: 'flex', gap: '2px' }}>
              ⚠️ Exceeds Notional Exposure Limit ($10M)
            </div>
          )}

          <div
            style={{
              background: 'var(--bg-input)',
              padding: '4px 8px',
              borderRadius: '4px',
              fontSize: '10px',
              color: 'var(--text-muted)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              border: '1px solid var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
              <span>Est. Value:</span>
              <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
                <HelpCircle size={9} />
                <div className="tooltip-box">
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Estimated Value</span>
                  Computed as `Price * Quantity`. Represents the gross notional commitment for this order transaction.
                </div>
              </span>
            </div>
            <span className="mono" style={{ fontWeight: 700, color: isNotionalBreached ? 'var(--sell-red)' : 'var(--text-main)' }}>
              ${estimatedValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {errorMsg && (
            <div style={{ color: 'var(--sell-red)', fontSize: '9px', fontWeight: 700, textAlign: 'center', padding: '2px 0' }}>
              {errorMsg}
            </div>
          )}

          <button
            type="submit"
            className={`btn ${side === 'buy' ? 'btn-buy' : 'btn-sell'}`}
            disabled={isSubmitting || isQtyBreached || isNotionalBreached}
            style={{ width: '100%', padding: '6px 10px', height: '28px', fontSize: '11px', display: 'flex', gap: '4px', opacity: (isQtyBreached || isNotionalBreached) ? 0.4 : 1 }}
          >
            <Send size={12} /> {isSubmitting ? 'SENDING...' : `SEND ${side.toUpperCase()} ORDER`}
          </button>
        </div>
      </form>
    </div>
  );
};

