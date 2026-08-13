import React, { useMemo, useRef, useState, useEffect } from 'react';
import type { HistoryPoint } from '../types';
import { TrendingUp, HelpCircle } from 'lucide-react';

interface LiveMarketDataChartProps {
  history: HistoryPoint[];
  symbol: string;
  lastPrice: number;
  bestBid: number | null;
  bestAsk: number | null;
}

export const CandlestickChart: React.FC<LiveMarketDataChartProps> = ({
  history,
  symbol,
  lastPrice,
  bestBid,
  bestAsk,
}) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 160 });
  const [hoveredPoint, setHoveredPoint] = useState<HistoryPoint | null>(null);
  const [mouseX, setMouseX] = useState<number | null>(null);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const observer = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width, height } = entries[0].contentRect;
      setDimensions({ width: width || 600, height: height || 160 });
    });
    observer.observe(wrapperRef.current);
    return () => observer.disconnect();
  }, []);

  const width = dimensions.width;
  const height = dimensions.height;

  const paddingLeft = 45;
  const paddingRight = 60;
  const paddingTop = 15;
  const paddingBottom = 26;
  const chartW = width - paddingLeft - paddingRight;
  const chartH = height - paddingTop - paddingBottom;

  // Volume uses bottom 20% of chart
  const volumeH = chartH * 0.22;
  const priceH = chartH * 0.72;

  // Find min/max price bounds
  const priceBounds = useMemo(() => {
    if (history.length === 0) {
      return { min: lastPrice * 0.999, max: lastPrice * 1.001 };
    }
    const prices = history.map(h => h.price);
    if (bestBid) prices.push(bestBid);
    if (bestAsk) prices.push(bestAsk);

    let min = Math.min(...prices);
    let max = Math.max(...prices);

    // Give some padding
    const pad = (max - min) * 0.05 || 0.1;
    return { min: min - pad, max: max + pad };
  }, [history, lastPrice, bestBid, bestAsk]);

  const priceRange = priceBounds.max - priceBounds.min || 1;

  const getX = (index: number) => {
    if (history.length <= 1) return paddingLeft;
    return paddingLeft + (index / (history.length - 1)) * chartW;
  };

  const getPriceY = (price: number) => {
    return paddingTop + priceH - ((price - priceBounds.min) / priceRange) * priceH;
  };

  const maxVolume = useMemo(() => {
    if (history.length === 0) return 1;
    return Math.max(...history.map(h => h.volume)) || 1;
  }, [history]);

  const getVolumeY = (vol: number) => {
    const volPct = vol / maxVolume;
    return height - paddingBottom - volPct * volumeH;
  };

  // Coordinates mapping
  const points = useMemo(() => {
    return history.map((pt, i) => ({
      x: getX(i),
      y: getPriceY(pt.price),
      pt
    }));
  }, [history, chartW, priceH, priceBounds]);

  // Compute MA20 (Rolling 20-period simple moving average)
  const ma20Points = useMemo(() => {
    const pointsList: { x: number; y: number }[] = [];
    for (let i = 0; i < history.length; i++) {
      const subset = history.slice(Math.max(0, i - 19), i + 1);
      const sum = subset.reduce((acc, h) => acc + h.price, 0);
      const avg = sum / subset.length;
      pointsList.push({
        x: getX(i),
        y: getPriceY(avg),
      });
    }
    return pointsList;
  }, [history, chartW, priceH, priceBounds]);

  // SVG Paths
  const linePathStr = useMemo(() => {
    if (points.length === 0) return '';
    return points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  }, [points]);

  const areaPathStr = useMemo(() => {
    if (points.length === 0) return '';
    const first = points[0];
    const last = points[points.length - 1];
    const baseCloseY = paddingTop + priceH;
    return `M ${first.x.toFixed(1)},${baseCloseY.toFixed(1)} L ${linePathStr} L ${last.x.toFixed(1)},${baseCloseY.toFixed(1)} Z`;
  }, [points, linePathStr, priceH]);

  const maPathStr = useMemo(() => {
    if (ma20Points.length === 0) return '';
    return ma20Points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  }, [ma20Points]);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (history.length === 0 || !wrapperRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - paddingLeft;
    setMouseX(x + paddingLeft);

    const ratio = Math.max(0, Math.min(1, x / chartW));
    const index = Math.round(ratio * (history.length - 1));
    if (index >= 0 && index < history.length) {
      setHoveredPoint(history[index]);
    } else {
      setHoveredPoint(null);
    }
  };

  const handleMouseLeave = () => {
    setHoveredPoint(null);
    setMouseX(null);
  };

  const spread = bestAsk && bestBid ? bestAsk - bestBid : 0;
  const currentPriceY = getPriceY(lastPrice);

  return (
    <div className="terminal-panel" style={{ padding: '8px 12px', height: '100%', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {/* Chart Panel Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <TrendingUp size={12} color="var(--accent-cyan)" />
          <span style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            {symbol} Live Market Data
          </span>
          <span className="tooltip-trigger" style={{ color: 'var(--text-dim)' }}>
            <HelpCircle size={10} style={{ cursor: 'pointer' }} />
            <div className="tooltip-box" style={{ width: '180px' }}>
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 800, display: 'block', marginBottom: '2px' }}>Market Data Stream</span>
              Plots real-time tick prices and volume directly generated by the Python simulator loop. MA20 represents a rolling 20-tick simple moving average.
            </div>
          </span>
        </div>

        {/* Live quote values */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
          {hoveredPoint ? (
            <div className="mono" style={{ fontSize: '9px', display: 'flex', gap: '6px', color: 'var(--text-muted)' }}>
              <span>Price:<span style={{ color: 'var(--accent-cyan)' }}>${hoveredPoint.price.toFixed(2)}</span></span>
              <span>Vol:<span style={{ color: 'var(--text-main)' }}>{hoveredPoint.volume}</span></span>
              <span>Spread:<span style={{ color: 'var(--text-dim)' }}>${(hoveredPoint.ask - hoveredPoint.bid).toFixed(2)}</span></span>
            </div>
          ) : (
            <div className="mono" style={{ fontSize: '9px', display: 'flex', gap: '8px', color: 'var(--text-dim)' }}>
              <span>MA20: <span style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>
                {ma20Points.length > 0 ? `$${history.length > 0 ? (history.slice(-20).reduce((sum, h) => sum + h.price, 0) / Math.min(20, history.length)).toFixed(2) : '--'}` : '--'}
              </span></span>
              <span>Spread: <span style={{ color: 'var(--accent-cyan)' }}>${spread.toFixed(2)}</span></span>
            </div>
          )}
          <div className="mono" style={{ fontSize: '12px', fontWeight: 800, color: 'var(--accent-cyan)' }}>
            ${lastPrice.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Description */}
      <p className="chart-panel-desc" style={{ fontSize: '8px', color: 'var(--text-dim)', marginBottom: '6px', marginTop: '-2px', lineHeight: 1.3, flexShrink: 0 }}>
        Visualizes the real-time transaction price activity and volume ticks generated directly from the simulator's matching engine loop.
      </p>

      {/* SVG Canvas Area */}
      <div ref={wrapperRef} style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        {history.length === 0 ? (
          <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: 'var(--text-dim)' }}>
            Connecting market data tick stream...
          </div>
        ) : (
          <svg
            width="100%"
            height="100%"
            viewBox={`0 0 ${width} ${height}`}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', overflow: 'hidden' }}
          >
            <defs>
              <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity="0.25" />
                <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Grid horizontal lines */}
            <line x1={paddingLeft} y1={getPriceY(priceBounds.max)} x2={paddingLeft + chartW} y2={getPriceY(priceBounds.max)} stroke="var(--border-color)" strokeDasharray="2 4" strokeWidth={0.5} />
            <line x1={paddingLeft} y1={getPriceY((priceBounds.max + priceBounds.min) / 2)} x2={paddingLeft + chartW} y2={getPriceY((priceBounds.max + priceBounds.min) / 2)} stroke="var(--border-color)" strokeDasharray="2 4" strokeWidth={0.5} />
            <line x1={paddingLeft} y1={getPriceY(priceBounds.min)} x2={paddingLeft + chartW} y2={getPriceY(priceBounds.min)} stroke="var(--border-color)" strokeDasharray="2 4" strokeWidth={0.5} />

            {/* Y-Axis Label: Price */}
            <text
              transform={`rotate(-90, 10, ${paddingTop + priceH / 2})`}
              x={10}
              y={paddingTop + priceH / 2}
              fill="var(--text-dim)"
              fontSize="7px"
              fontWeight={700}
              textAnchor="middle"
              letterSpacing="0.5px"
            >
              PRICE ($)
            </text>

            {/* Area under line chart */}
            {areaPathStr && (
              <path
                d={areaPathStr}
                fill="url(#areaGradient)"
                stroke="none"
              />
            )}

            {/* Price Line Chart */}
            {linePathStr && (
              <polyline
                fill="none"
                stroke="var(--accent-cyan)"
                strokeWidth="1.5"
                points={linePathStr}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* MA20 simple moving average line */}
            {maPathStr && (
              <polyline
                fill="none"
                stroke="var(--accent-amber)"
                strokeWidth="1.0"
                points={maPathStr}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={0.7}
              />
            )}

            {/* Volume Chart Identifier Line */}
            <line
              x1={paddingLeft}
              y1={height - paddingBottom - volumeH}
              x2={paddingLeft + chartW}
              y2={height - paddingBottom - volumeH}
              stroke="rgba(255,255,255,0.06)"
              strokeWidth={0.8}
            />

            {/* Volume Bars */}
            {history.map((h, i) => {
              const barX = getX(i);
              const barY = getVolumeY(h.volume);
              const barW = Math.max(1.5, chartW / history.length - 1);
              const isUp = i > 0 ? h.price >= history[i - 1].price : true;
              return (
                <rect
                  key={`vol-${h.timestamp}-${i}`}
                  x={barX - barW / 2}
                  y={barY}
                  width={barW}
                  height={Math.max(1, height - paddingBottom - barY)}
                  fill={isUp ? 'rgba(0, 230, 118, 0.25)' : 'rgba(255, 23, 68, 0.25)'}
                />
              );
            })}

            {/* Volume label indicator */}
            <text
              x={paddingLeft + 4}
              y={height - paddingBottom - volumeH + 7}
              fill="var(--text-dim)"
              fontSize="6.5px"
              fontWeight={700}
              letterSpacing="0.2px"
            >
              VOLUME (shs)
            </text>

            {/* Time X-Axis label */}
            <text
              x={paddingLeft + chartW / 2}
              y={height - 4}
              fill="var(--text-dim)"
              fontSize="7px"
              fontWeight={700}
              textAnchor="middle"
              letterSpacing="0.5px"
            >
              TIME (ticks over session)
            </text>

            {/* Horizontal Line at Current Price */}
            <line
              x1={paddingLeft}
              y1={currentPriceY}
              x2={paddingLeft + chartW}
              y2={currentPriceY}
              stroke="rgba(0, 229, 255, 0.25)"
              strokeDasharray="2 2"
              strokeWidth={0.8}
            />

            {/* Interactive Crosshair */}
            {mouseX !== null && mouseX >= paddingLeft && mouseX <= paddingLeft + chartW && (
              <g>
                <line
                  x1={mouseX}
                  y1={paddingTop}
                  x2={mouseX}
                  y2={height - paddingBottom}
                  stroke="rgba(255,255,255,0.2)"
                  strokeDasharray="3 3"
                  strokeWidth={0.6}
                />
                {hoveredPoint && (
                  <line
                    x1={paddingLeft}
                    y1={getPriceY(hoveredPoint.price)}
                    x2={paddingLeft + chartW}
                    y2={getPriceY(hoveredPoint.price)}
                    stroke="rgba(255,255,255,0.2)"
                    strokeDasharray="3 3"
                    strokeWidth={0.6}
                  />
                )}
              </g>
            )}

            {/* Y-Axis Price values (drawn on the right side) */}
            <text x={paddingLeft + chartW + 6} y={getPriceY(priceBounds.max) + 3} fill="var(--text-dim)" fontSize="8px" className="mono" fontWeight={600}>
              ${priceBounds.max.toFixed(2)}
            </text>
            <text x={paddingLeft + chartW + 6} y={getPriceY((priceBounds.max + priceBounds.min) / 2) + 3} fill="var(--text-dim)" fontSize="8px" className="mono" fontWeight={600}>
              ${((priceBounds.max + priceBounds.min) / 2).toFixed(2)}
            </text>
            <text x={paddingLeft + chartW + 6} y={getPriceY(priceBounds.min) + 3} fill="var(--text-dim)" fontSize="8px" className="mono" fontWeight={600}>
              ${priceBounds.min.toFixed(2)}
            </text>

            {/* Latest Price Right Bubble overlay */}
            <g transform={`translate(${paddingLeft + chartW}, ${currentPriceY - 6})`}>
              <rect width={48} height={12} fill="var(--accent-cyan-bg)" stroke="var(--accent-cyan)" strokeWidth={0.5} rx={2} x={2} />
              <text x={6} y={9} fill="var(--accent-cyan)" fontSize="7px" className="mono" fontWeight={700}>
                ${lastPrice.toFixed(2)}
              </text>
            </g>
          </svg>
        )}
      </div>
    </div>
  );
};
