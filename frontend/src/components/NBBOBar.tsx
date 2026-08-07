/**
 * NBBOBar — Inside Market Quote Banner
 *
 * Displays the current symbol's best bid, best ask, and spread as a
 * permanently-visible bar beneath the execution pipeline banner.
 *
 * MarketRouter is not wired into web_server.py, so the system operates in
 * single-venue mode. This label is shown explicitly so the architecture
 * limitation is transparent rather than implied.
 *
 * All values come directly from the WebSocket SNAPSHOT payload fields
 * best_bid, best_ask, and spread — no computation or backend changes needed.
 */

interface Props {
  bestBid: number | null;
  bestAsk: number | null;
  spread: number;
  symbol: string;
  isConnected: boolean;
}

export function NBBOBar({ bestBid, bestAsk, spread, symbol, isConnected }: Props) {
  const live = isConnected && bestBid !== null && bestAsk !== null;

  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)',
        padding: 'var(--nbbo-pad-y, 4px) var(--pad-x, 16px)',
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        flexShrink: 0,
        fontSize: '11px',
        fontFamily: 'monospace',
        userSelect: 'none',
      }}
    >
      {/* Venue label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span
          style={{
            color: 'var(--text-dim)',
            fontWeight: 600,
            letterSpacing: '0.06em',
            fontSize: '10px',
          }}
        >
          VENUE ROUTING
        </span>
        <span
          style={{
            background: 'rgba(100,116,139,0.18)',
            color: 'var(--text-dim)',
            padding: '1px 5px',
            borderRadius: '3px',
            fontSize: '10px',
            fontWeight: 700,
            letterSpacing: '0.07em',
          }}
        >
          SINGLE VENUE MODE
        </span>
      </div>

      <span style={{ color: 'var(--border-color)' }}>│</span>

      {/* Active symbol */}
      <span
        style={{
          color: 'var(--text-primary)',
          fontWeight: 700,
          letterSpacing: '0.05em',
          fontSize: '11px',
        }}
      >
        {symbol}
      </span>

      <span style={{ color: 'var(--border-color)' }}>│</span>

      {/* Best Bid */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span style={{ color: 'var(--text-dim)', fontSize: '10px', letterSpacing: '0.04em' }}>
          BEST BID
        </span>
        <span
          style={{
            color: live ? 'var(--accent-green)' : 'var(--text-dim)',
            fontWeight: 700,
            fontSize: '12px',
          }}
        >
          {live ? `$${bestBid!.toFixed(2)}` : '—'}
        </span>
      </div>

      {/* Best Ask */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span style={{ color: 'var(--text-dim)', fontSize: '10px', letterSpacing: '0.04em' }}>
          BEST ASK
        </span>
        <span
          style={{
            color: live ? 'var(--accent-red)' : 'var(--text-dim)',
            fontWeight: 700,
            fontSize: '12px',
          }}
        >
          {live ? `$${bestAsk!.toFixed(2)}` : '—'}
        </span>
      </div>

      {/* Spread */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <span style={{ color: 'var(--text-dim)', fontSize: '10px', letterSpacing: '0.04em' }}>
          SPREAD
        </span>
        <span
          style={{
            color: live && spread > 0 ? 'var(--accent-cyan)' : 'var(--text-dim)',
            fontWeight: 700,
            fontSize: '12px',
          }}
        >
          {live ? `$${spread.toFixed(2)}` : '—'}
        </span>
      </div>

      {/* Connection indicator — pushed to the far right */}
      <div
        style={{
          marginLeft: 'auto',
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            background: isConnected ? 'var(--accent-green)' : 'var(--accent-red)',
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
        <span style={{ color: 'var(--text-dim)', fontSize: '10px', letterSpacing: '0.04em' }}>
          {isConnected ? 'LIVE' : 'DISCONNECTED'}
        </span>
      </div>
    </div>
  );
}
