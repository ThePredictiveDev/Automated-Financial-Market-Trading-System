import React, { useEffect, useRef, useState } from 'react';
import type { DepthLevel } from '../types';
import { Layers, HelpCircle } from 'lucide-react';

interface OrderBookProps {
  bids: DepthLevel[];
  asks: DepthLevel[];
  bestBid: number | null;
  bestAsk: number | null;
  spread: number;
}

export const OrderBook: React.FC<OrderBookProps> = ({
  bids,
  asks,
  bestBid,
  bestAsk,
  spread,
}) => {
  const prevQuantities = useRef<Record<number, number>>({});
  const [flashStates, setFlashStates] = useState<Record<number, 'up' | 'down'>>({});

  useEffect(() => {
    const nextFlash: Record<number, 'up' | 'down'> = {};
    
    // Check bids updates for flash triggers
    bids.forEach(b => {
      const prev = prevQuantities.current[b.price];
      if (prev !== undefined && prev !== b.quantity) {
        nextFlash[b.price] = b.quantity > prev ? 'up' : 'down';
      }
      prevQuantities.current[b.price] = b.quantity;
    });

    // Check asks updates for flash triggers
    asks.forEach(a => {
      const prev = prevQuantities.current[a.price];
      if (prev !== undefined && prev !== a.quantity) {
        nextFlash[a.price] = a.quantity > prev ? 'up' : 'down';
      }
      prevQuantities.current[a.price] = a.quantity;
    });

    if (Object.keys(nextFlash).length > 0) {
      setFlashStates(prev => ({ ...prev, ...nextFlash }));
      const timer = setTimeout(() => {
        setFlashStates({});
      }, 400);
      return () => clearTimeout(timer);
    }
  }, [bids, asks]);

  // Aggregate cumulative depth for Bids
  let cumBid = 0;
  const bidsWithCum = bids.slice(0, 10).map(b => {
    cumBid += b.quantity;
    return { ...b, cumQty: cumBid };
  });

  // Aggregate cumulative depth for Asks
  let cumAsk = 0;
  const asksWithCum = asks.slice(0, 10).map(a => {
    cumAsk += a.quantity;
    return { ...a, cumQty: cumAsk };
  });

  const totalBidDepth = bidsWithCum[bidsWithCum.length - 1]?.cumQty || 1;
  const totalAskDepth = asksWithCum[asksWithCum.length - 1]?.cumQty || 1;
  const maxCum = Math.max(totalBidDepth, totalAskDepth);

  const midPrice = bestBid && bestAsk ? (bestBid + bestAsk) / 2 : null;

  return (
    <div className="terminal-panel" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Title Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Layers size={12} color="var(--accent-cyan)" />
          <h3 style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Level 2 Order Book
          </h3>
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
            <HelpCircle size={10} style={{ cursor: 'pointer' }} />
            <div className="tooltip-box">
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Limit Order Book</span>
              Maintains queues of buy limit orders (Bids) and sell limit orders (Asks). Level 2 depth groups orders by price level, sorting by price-time priority.
            </div>
          </span>
        </div>
        <div className="tooltip-trigger" style={{ fontSize: '9px', color: 'var(--text-dim)', fontWeight: 600 }}>
          <span>Price-Time Priority</span>
          <div className="tooltip-box">
            <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Execution Priority</span>
            Continuous double auction priority rules dictate that orders at better prices execute first, followed by orders that arrived earliest at that price level.
          </div>
        </div>
      </div>
      <p style={{ fontSize: '8px', color: 'var(--text-dim)', marginBottom: '4.5px', marginTop: '-2px', lineHeight: 1.35 }}>
        All resting buy (bid) and sell (ask) limit orders ranked by price-time priority. <strong>Flow Interaction:</strong> Feeds the Matching Engine; incoming crossing orders immediately execute against these resting levels, updating portfolios and streams.
      </p>

      {/* Grid Header Columns */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr',
          padding: '2px 4px',
          fontSize: '9px',
          fontWeight: 700,
          color: 'var(--text-dim)',
          textTransform: 'uppercase',
          borderBottom: '1px solid var(--border-color)',
          marginBottom: '2px',
        }}
      >
        <span>Price ($)</span>
        <span style={{ textAlign: 'right' }}>Size</span>
        <span className="tooltip-trigger" style={{ textAlign: 'right', display: 'block' }}>
          <span>Cum. Depth</span>
          <div className="tooltip-box" style={{ left: 'auto', right: 0, transform: 'none' }}>
            <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Cumulative Depth</span>
            Sum of size from the inside market (spread) to this price. Highlights total liquid supply at this boundary.
          </div>
        </span>
      </div>

      {/* Asks (Sells) - Displayed worst on top, best on bottom */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column-reverse', minHeight: 0 }}>
        {asksWithCum.map((ask) => {
          const depthPercent = (ask.cumQty / maxCum) * 100;
          const flash = flashStates[ask.price];
          const flashClass = flash === 'up' ? 'flash-bid-up' : flash === 'down' ? 'flash-bid-down' : '';
          return (
            <div
              key={`ask-${ask.price}`}
              className={flashClass}
              style={{
                position: 'relative',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                padding: '1px 4px',
                fontSize: '11px',
                height: '18px',
                alignItems: 'center',
              }}
            >
              <div className="depth-bar-ask" style={{ width: `${depthPercent}%` }} />
              <span className="mono" style={{ color: 'var(--sell-red)', fontWeight: 700, zIndex: 1 }}>
                {ask.price.toFixed(2)}
              </span>
              <span className="mono" style={{ textAlign: 'right', color: 'var(--text-main)', zIndex: 1 }}>
                {ask.quantity.toLocaleString()}
              </span>
              <span className="mono" style={{ textAlign: 'right', color: 'var(--text-dim)', fontSize: '9px', zIndex: 1 }}>
                {ask.cumQty.toLocaleString()}
              </span>
            </div>
          );
        })}
        {asksWithCum.length === 0 && (
          <div style={{ fontSize: '10px', color: 'var(--text-dim)', textAlign: 'center', padding: '10px 0' }}>No Ask Orders</div>
        )}
      </div>

      {/* Inside Market Spread Summary */}
      <div
        style={{
          margin: '4px 0',
          padding: '4px 8px',
          background: 'var(--bg-input)',
          borderRadius: '4px',
          border: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '10px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
          <span style={{ fontSize: '8px', color: 'var(--text-dim)', fontWeight: 600 }}>Mid Market Price</span>
          <span className="mono" style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '11px' }}>
            {midPrice ? `$${midPrice.toFixed(2)}` : '--'}
          </span>
        </div>
        
        <div className="tooltip-trigger" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '1px' }}>
          <span style={{ fontSize: '8px', color: 'var(--text-dim)', fontWeight: 600 }}>Bid-Ask Spread</span>
          <span className="mono" style={{ fontWeight: 700, color: 'var(--accent-cyan)', fontSize: '11px' }}>
            ${spread.toFixed(2)}
          </span>
          <div className="tooltip-box" style={{ left: 'auto', right: 0, transform: 'none' }}>
            <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Spread</span>
            The cost of trading. Difference between best bid (${bestBid?.toFixed(2) || '--'}) and best ask (${bestAsk?.toFixed(2) || '--'}).
          </div>
        </div>
      </div>

      {/* Bids (Buys) - Displayed best on top, worst on bottom */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {bidsWithCum.map((bid) => {
          const depthPercent = (bid.cumQty / maxCum) * 100;
          const flash = flashStates[bid.price];
          const flashClass = flash === 'up' ? 'flash-bid-up' : flash === 'down' ? 'flash-bid-down' : '';
          return (
            <div
              key={`bid-${bid.price}`}
              className={flashClass}
              style={{
                position: 'relative',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                padding: '1px 4px',
                fontSize: '11px',
                height: '18px',
                alignItems: 'center',
              }}
            >
              <div className="depth-bar-bid" style={{ width: `${depthPercent}%` }} />
              <span className="mono" style={{ color: 'var(--buy-green)', fontWeight: 700, zIndex: 1 }}>
                {bid.price.toFixed(2)}
              </span>
              <span className="mono" style={{ textAlign: 'right', color: 'var(--text-main)', zIndex: 1 }}>
                {bid.quantity.toLocaleString()}
              </span>
              <span className="mono" style={{ textAlign: 'right', color: 'var(--text-dim)', fontSize: '9px', zIndex: 1 }}>
                {bid.cumQty.toLocaleString()}
              </span>
            </div>
          );
        })}
        {bidsWithCum.length === 0 && (
          <div style={{ fontSize: '10px', color: 'var(--text-dim)', textAlign: 'center', padding: '10px 0' }}>No Bid Orders</div>
        )}
      </div>
    </div>
  );
};

