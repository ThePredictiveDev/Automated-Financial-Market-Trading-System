"""
Replay server for deterministic playback of recorded trading sessions.

Provides WebSocket streaming and REST API controls for:
- Loading recorded sessions
- Playing/pausing/seeking through events
- Adjustable playback speed
- Step-by-step navigation
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PlaybackMode(Enum):
    """Playback state machine states."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"


class ReplayServer:
    """
    Manages playback of recorded trading sessions.
    
    Streams events via WebSocket with timing control, seeking,
    and speed adjustment capabilities.
    """
    
    def __init__(self, sessions_dir: str = "replay_sessions"):
        self.sessions_dir = Path(sessions_dir)
        
        # Playback state
        self.mode = PlaybackMode.STOPPED
        self.events: List[Dict[str, Any]] = []
        self.current_index = 0
        self.playback_speed = 1.0
        self.session_metadata: Optional[Dict[str, Any]] = None
        
        # Timing
        self.session_start_ts: Optional[float] = None
        self.session_end_ts: Optional[float] = None
        self.replay_start_time: Optional[float] = None
        self.pause_time: Optional[float] = None
        self.time_offset = 0.0  # Accumulated pause duration
        
        # WebSocket connections
        self.connections: set = set()
        
        # Background playback task
        self.playback_task: Optional[asyncio.Task] = None
    
    async def load_session(self, filename: str) -> Dict[str, Any]:
        """
        Load a recorded session file and broadcast initial state.
        
        Args:
            filename: Session filename (e.g., "session_20260729_014230.jsonl")
            
        Returns:
            Session metadata (duration, event_count, etc.)
        """
        session_path = self.sessions_dir / filename
        if not session_path.exists():
            raise FileNotFoundError(f"Session file not found: {filename}")
        
        # Load all events
        self.events = []
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    self.events.append(event)
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed line in {filename}")
        
        if not self.events:
            raise ValueError(f"No valid events in session file: {filename}")
        
        # Extract metadata
        self.session_start_ts = self.events[0].get('ts')
        self.session_end_ts = self.events[-1].get('ts')
        duration = self.session_end_ts - self.session_start_ts if self.session_start_ts and self.session_end_ts else 0
        
        # Extract session start data if available
        session_start_event = next((e for e in self.events if e.get('type') == 'SESSION_START'), None)
        session_config = session_start_event.get('data', {}) if session_start_event else {}
        
        self.session_metadata = {
            "filename": filename,
            "event_count": len(self.events),
            "duration": duration,
            "start_ts": self.session_start_ts,
            "end_ts": self.session_end_ts,
            "config": session_config
        }
        
        # Reset playback state
        self.current_index = 0
        self.mode = PlaybackMode.STOPPED
        self.replay_start_time = None
        self.pause_time = None
        self.time_offset = 0.0
        
        # Broadcast initial state to connected clients
        initial_state = self._build_initial_state()
        if initial_state and self.connections:
            await self._broadcast_reconstructed_snapshot(initial_state, self.events[0] if self.events else {})
        
        logger.info(f"Loaded session: {filename} ({len(self.events)} events, {duration:.1f}s)")
        
        return self.session_metadata
    
    async def play(self) -> Dict[str, Any]:
        """Start or resume playback."""
        if not self.events:
            raise RuntimeError("No session loaded")
        
        if self.mode == PlaybackMode.COMPLETED:
            # Restart from beginning. seek() only flips mode back to PLAYING
            # when playback was already in progress before the seek, which is
            # never true here (mode is COMPLETED) — so without explicitly
            # resetting to STOPPED, mode would stay COMPLETED and neither
            # branch below would fire, silently ignoring the Play click.
            await self.seek(0)
            self.mode = PlaybackMode.STOPPED
        
        if self.mode == PlaybackMode.PAUSED:
            # Resume from pause - adjust time offset
            if self.pause_time:
                self.time_offset += time.time() - self.pause_time
            self.mode = PlaybackMode.PLAYING
        elif self.mode == PlaybackMode.STOPPED:
            # Start from current index
            self.replay_start_time = time.time()
            self.time_offset = 0.0
            self.mode = PlaybackMode.PLAYING
            
            # Start background playback task
            if self.playback_task:
                self.playback_task.cancel()
            self.playback_task = asyncio.create_task(self._playback_loop())
        
        return self.get_status()
    
    async def pause(self) -> Dict[str, Any]:
        """Pause playback."""
        if self.mode == PlaybackMode.PLAYING:
            self.mode = PlaybackMode.PAUSED
            self.pause_time = time.time()
        
        return self.get_status()
    
    async def stop(self) -> Dict[str, Any]:
        """Stop playback and reset to beginning."""
        if self.playback_task:
            self.playback_task.cancel()
            self.playback_task = None
        
        self.mode = PlaybackMode.STOPPED
        self.current_index = 0
        self.replay_start_time = None
        self.pause_time = None
        self.time_offset = 0.0
        
        return self.get_status()
    
    async def seek(self, target: int | float) -> Dict[str, Any]:
        """
        Seek to a specific position and reconstruct state at that point.
        
        Args:
            target: Event index (int) or timestamp (float) or progress ratio (0.0-1.0)
        """
        if not self.events:
            raise RuntimeError("No session loaded")
        
        was_playing = self.mode == PlaybackMode.PLAYING
        if was_playing:
            await self.pause()
        
        if isinstance(target, int):
            # Seek by index
            self.current_index = max(0, min(target, len(self.events) - 1))
        elif 0.0 <= target <= 1.0:
            # Seek by progress ratio
            self.current_index = int(target * (len(self.events) - 1))
        else:
            # Seek by timestamp
            for i, event in enumerate(self.events):
                if event.get('ts', 0) >= target:
                    self.current_index = i
                    break
        
        # Reconstruct state at target position
        reconstructed_state = self._reconstruct_state_at_index(self.current_index)
        current_event = self.events[self.current_index]
        
        # Broadcast reconstructed state
        await self._broadcast_reconstructed_snapshot(reconstructed_state, current_event)
        
        if was_playing:
            # Adjust timing for new position
            if self.session_start_ts:
                elapsed_in_session = self.events[self.current_index].get('ts', 0) - self.session_start_ts
                self.replay_start_time = time.time() - (elapsed_in_session / self.playback_speed)
                self.time_offset = 0.0
            await self.play()
        
        return self.get_status()
    
    def _reconstruct_state_at_index(self, target_index: int) -> Dict[str, Any]:
        """
        Reconstruct the complete market state at a specific event index.
        
        Strategy: Find the most recent CHECKPOINT before target, then apply
        all events from that checkpoint to target.
        """
        # Find the most recent checkpoint before target
        checkpoint_index = -1
        checkpoint_state = None
        
        for i in range(target_index, -1, -1):
            if self.events[i].get('type') == 'CHECKPOINT':
                checkpoint_index = i
                checkpoint_state = self.events[i].get('data', {})
                break
        
        # If no checkpoint found, start from initial state
        if checkpoint_state is None:
            checkpoint_state = self._build_initial_state()
            checkpoint_index = -1
        
        # Apply all events from checkpoint to target
        current_state = checkpoint_state
        for i in range(checkpoint_index + 1, target_index + 1):
            event = self.events[i]
            updated_state = self._apply_event_to_state(current_state, event)
            if updated_state:
                current_state = updated_state
        
        return current_state
    
    async def step(self, direction: int = 1) -> Dict[str, Any]:
        """
        Step forward or backward by N events and reconstruct state.
        
        Args:
            direction: Number of events to step (positive=forward, negative=backward)
        """
        if not self.events:
            raise RuntimeError("No session loaded")
        
        self.current_index = max(0, min(self.current_index + direction, len(self.events) - 1))
        
        # Reconstruct state at new position
        reconstructed_state = self._reconstruct_state_at_index(self.current_index)
        current_event = self.events[self.current_index]
        
        # Broadcast reconstructed state
        await self._broadcast_reconstructed_snapshot(reconstructed_state, current_event)
        
        # Also emit lifecycle event if this is a lifecycle event
        if current_event.get('type') == 'LIFECYCLE':
            await self._broadcast_event(current_event, is_step=True)
        
        return self.get_status()
    
    def set_speed(self, speed: float) -> Dict[str, Any]:
        """
        Set playback speed multiplier.
        
        Args:
            speed: Multiplier (0.25x, 0.5x, 1x, 2x, 5x, etc.)
        """
        self.playback_speed = max(0.1, min(speed, 10.0))
        
        # If currently playing, adjust timing reference
        if self.mode == PlaybackMode.PLAYING and self.replay_start_time and self.session_start_ts:
            current_event = self.events[self.current_index] if self.current_index < len(self.events) else None
            if current_event:
                elapsed_in_session = current_event.get('ts', 0) - self.session_start_ts
                self.replay_start_time = time.time() - (elapsed_in_session / self.playback_speed)
                self.time_offset = 0.0
        
        return self.get_status()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current playback status."""
        progress = 0.0
        current_ts = None
        current_event_info = None
        
        if self.events and self.current_index < len(self.events):
            progress = self.current_index / max(1, len(self.events) - 1)
            current_event = self.events[self.current_index]
            current_ts = current_event.get('ts')
            current_event_info = {
                "seq": current_event.get('seq'),
                "type": current_event.get('type'),
                "data_preview": str(current_event.get('data', {}))[:100]
            }
        
        elapsed = 0.0
        if self.session_start_ts and current_ts:
            elapsed = current_ts - self.session_start_ts
        
        return {
            "mode": self.mode.value,
            "loaded": self.session_metadata is not None,
            "session": self.session_metadata,
            "current_index": self.current_index,
            "total_events": len(self.events),
            "progress": progress,
            "playback_speed": self.playback_speed,
            "elapsed": elapsed,
            "current_event": current_event_info
        }
    
    async def _playback_loop(self):
        """Background task that streams events at correct timing."""
        try:
            # Build initial state from first checkpoint or session start
            current_state = self._build_initial_state()
            
            while self.mode == PlaybackMode.PLAYING and self.current_index < len(self.events):
                current_event = self.events[self.current_index]
                current_ts = current_event.get('ts')
                event_type = current_event.get('type')
                
                if current_ts and self.session_start_ts and self.replay_start_time:
                    # Calculate when this event should be emitted
                    elapsed_in_session = current_ts - self.session_start_ts
                    target_real_time = self.replay_start_time + (elapsed_in_session / self.playback_speed) + self.time_offset
                    
                    # Wait until target time
                    now = time.time()
                    wait_time = target_real_time - now
                    
                    if wait_time > 0:
                        # Wait in small chunks to allow for pause/stop
                        while wait_time > 0 and self.mode == PlaybackMode.PLAYING:
                            chunk = min(wait_time, 0.05)  # Check status every 50ms
                            await asyncio.sleep(chunk)
                            wait_time -= chunk
                
                # Check if still playing (might have been paused during sleep)
                if self.mode != PlaybackMode.PLAYING:
                    break
                
                # Update state based on event and broadcast
                updated_state = self._apply_event_to_state(current_state, current_event)
                if updated_state:
                    current_state = updated_state
                    await self._broadcast_reconstructed_snapshot(current_state, current_event)
                
                # Always broadcast lifecycle events for Order Journey
                if event_type == 'LIFECYCLE':
                    await self._broadcast_event(current_event)
                
                # Move to next
                self.current_index += 1
            
            # Reached end — clamp index back to the last valid event so status
            # (progress/current_event) correctly reports 100% instead of resetting
            # to a blank/zero state once current_index runs past len(events).
            if self.current_index >= len(self.events):
                self.current_index = len(self.events) - 1
                self.mode = PlaybackMode.COMPLETED
                await self._broadcast_session_summary()
        
        except asyncio.CancelledError:
            logger.info("Playback loop cancelled")
        except Exception as e:
            logger.error(f"Playback loop error: {e}", exc_info=True)
    
    def _empty_state_shape(self) -> Dict[str, Any]:
        """Baseline full-shape state so every field the UI expects is always present."""
        return {
            "bids": [],
            "asks": [],
            "history": [],
            "recent_trades": [],
            "portfolio": {"cash": 1000000, "realized_pnl": 0, "net_liq": 1000000, "positions": {}},
            "strategy_states": {},
            "user_orders": [],
            "best_bid": None,
            "best_ask": None,
            "spread": 0,
            "last_price": 0,
            "symbol": "AAPL",
            "symbols": ["AAPL"]
        }
    
    def _build_initial_state(self) -> Dict[str, Any]:
        """
        Build initial state, preferring a CHECKPOINT (full snapshot: order book,
        price history, portfolio, user orders, strategy states) over SESSION_START
        (which only carries session configuration, not market state).
        
        Recordings made before checkpoints-at-start was introduced may have no
        CHECKPOINT at all — in that case we fall back to a full-shape default
        seeded with whatever SESSION_START configuration is available, so older
        recordings still replay without crashing (order book/chart just build up
        progressively from TICK/TRADE events instead of starting fully populated).
        """
        session_start_data: Optional[Dict[str, Any]] = None
        
        for event in self.events:
            if event.get('type') == 'CHECKPOINT':
                return event.get('data', {})
            if event.get('type') == 'SESSION_START' and session_start_data is None:
                session_start_data = event.get('data', {})
        
        base = self._empty_state_shape()
        if session_start_data:
            base['symbols'] = session_start_data.get('symbols', base['symbols'])
            base['symbol'] = session_start_data.get('active_symbol', base['symbol'])
            base['strategy_states'] = session_start_data.get('strategy_states', base['strategy_states'])
            initial_portfolio = session_start_data.get('initial_portfolio')
            if initial_portfolio:
                base['portfolio'] = {
                    "cash": initial_portfolio.get('cash', base['portfolio']['cash']),
                    "realized_pnl": initial_portfolio.get('realized_pnl', 0),
                    "net_liq": initial_portfolio.get('cash', base['portfolio']['cash']),
                    "positions": initial_portfolio.get('positions', {}),
                }
            base_prices = session_start_data.get('base_prices', {})
            if base_prices and base['symbol'] in base_prices:
                base['last_price'] = base_prices[base['symbol']]
        
        return base
    
    def _apply_event_to_state(self, state: Dict[str, Any], event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Apply an event to the current state and return updated state.
        Returns None if event doesn't modify state (like LIFECYCLE events).
        """
        event_type = event.get('type')
        data = event.get('data', {})
        
        if event_type == 'CHECKPOINT':
            # Checkpoint is a full state replacement
            return data
        
        elif event_type == 'TICK':
            # Update last price and add to history. Only apply ticks for the
            # symbol currently being viewed/recorded to avoid mixing prices
            # from multiple symbols into one price series.
            symbol = data.get('symbol')
            price = data.get('price')
            
            if not symbol or price is None or symbol != state.get('symbol'):
                return None
            
            new_state = dict(state)
            new_state['last_price'] = price
            
            # Carry forward best_bid/best_ask so the chart's bid/ask fields and
            # spread stay populated between checkpoints instead of becoming
            # undefined (which previously produced NaN volume-bar heights).
            best_bid = new_state.get('best_bid') or round(price - 0.05, 2)
            best_ask = new_state.get('best_ask') or round(price + 0.05, 2)
            
            history = list(new_state.get('history', []))
            history.append({
                "price": price,
                "timestamp": event.get('ts'),
                "bid": best_bid,
                "ask": best_ask,
                "volume": 0,
            })
            new_state['history'] = history[-60:]
            
            return new_state
        
        elif event_type == 'TRADE':
            # Add trade to recent trades
            new_state = dict(state)
            recent_trades = list(new_state.get('recent_trades', []))
            recent_trades.insert(0, data)
            new_state['recent_trades'] = recent_trades[:20]  # Keep last 20
            
            # Update portfolio if this is a user trade
            # Note: Bot trades are handled by bot_portfolio, not shown in user portfolio
            
            return new_state
        
        elif event_type == 'STRATEGY_TOGGLE':
            # Update strategy states
            new_state = dict(state)
            strategy_states = dict(new_state.get('strategy_states', {}))
            strategy_name = data.get('strategy')
            enabled = data.get('enabled')
            
            if strategy_name:
                strategy_states[strategy_name] = enabled
                new_state['strategy_states'] = strategy_states
            
            return new_state
        
        elif event_type in ['USER_ORDER', 'USER_CANCEL']:
            # These will be reflected in next checkpoint's user_orders
            # For now, return None to skip state update
            return None
        
        elif event_type in ['LIFECYCLE', 'SESSION_START', 'SESSION_END']:
            # These don't modify market state
            return None
        
        return None
    
    async def _broadcast_reconstructed_snapshot(self, state: Dict[str, Any], source_event: Dict[str, Any]):
        """Broadcast a reconstructed SNAPSHOT event that looks like live data."""
        snapshot = {
            "type": "SNAPSHOT",
            **state,
            "replay_meta": {
                "index": self.current_index,
                "total": len(self.events),
                "progress": self.current_index / max(1, len(self.events) - 1),
                "mode": self.mode.value,
                "speed": self.playback_speed,
                "is_replay": True,
                "source_event_type": source_event.get('type')
            }
        }
        
        # Broadcast to all connections
        dead_connections = set()
        for ws in list(self.connections):
            try:
                await ws.send_json(snapshot)
            except Exception as e:
                logger.warning(f"Failed to send snapshot to WebSocket: {e}")
                dead_connections.add(ws)
        
        # Clean up dead connections
        self.connections -= dead_connections
    
    async def _broadcast_event(self, event: Dict[str, Any], is_seek: bool = False, is_step: bool = False):
        """
        Broadcast an event to all connected WebSocket clients.
        
        For LIFECYCLE events, the recorded shape is {type, data: {stage, order_id, ...}}
        but the live WebSocket shape (which the frontend's App.tsx parses) is flat:
        {type, stage, order_id, symbol, details, status, timestamp}. We flatten here
        so replayed order-journey / pipeline animations behave exactly like live mode.
        """
        event_type = event.get('type')
        data = event.get('data', {}) or {}
        
        if event_type == 'LIFECYCLE':
            outgoing: Dict[str, Any] = {
                "type": "LIFECYCLE",
                "order_id": data.get('order_id'),
                "symbol": data.get('symbol'),
                "timestamp": event.get('ts'),
                "stage": data.get('stage'),
                "status": data.get('status', 'SUCCESS'),
            }
            if data.get('details') is not None:
                outgoing['details'] = data.get('details')
        else:
            outgoing = dict(event)
        
        # Add replay metadata
        replay_event = {
            **outgoing,
            "replay_meta": {
                "index": self.current_index,
                "total": len(self.events),
                "progress": self.current_index / max(1, len(self.events) - 1),
                "mode": self.mode.value,
                "speed": self.playback_speed,
                "is_seek": is_seek,
                "is_step": is_step,
                "is_replay": True
            }
        }
        
        # Broadcast to all connections
        dead_connections = set()
        for ws in list(self.connections):
            try:
                await ws.send_json(replay_event)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.add(ws)
        
        # Clean up dead connections
        self.connections -= dead_connections
    
    async def _broadcast_session_summary(self):
        """Broadcast session summary when replay completes."""
        if not self.session_metadata:
            return
        
        # Calculate summary statistics
        summary = self._calculate_session_summary()
        
        summary_event = {
            "type": "REPLAY_SUMMARY",
            "data": summary,
            "replay_meta": {
                "mode": self.mode.value,
                "completed": True
            }
        }
        
        for ws in list(self.connections):
            try:
                await ws.send_json(summary_event)
            except:
                pass
    
    def _calculate_session_summary(self) -> Dict[str, Any]:
        """Calculate session statistics for summary display."""
        user_orders = 0
        executions = 0
        total_volume = 0
        spreads = []
        active_strategies = set()
        final_pnl = 0.0
        
        for event in self.events:
            event_type = event.get('type')
            data = event.get('data', {})
            
            if event_type == 'USER_ORDER':
                user_orders += 1
            
            elif event_type == 'TRADE':
                executions += 1
                total_volume += data.get('quantity', 0) * data.get('price', 0)
            
            elif event_type == 'STRATEGY_TOGGLE' and data.get('enabled'):
                active_strategies.add(data.get('strategy'))
            
            elif event_type == 'CHECKPOINT':
                # Extract spread from checkpoint
                checkpoint_data = data
                best_bid = checkpoint_data.get('best_bid')
                best_ask = checkpoint_data.get('best_ask')
                if best_bid and best_ask:
                    spreads.append(best_ask - best_bid)
                
                # Extract final P&L
                portfolio = checkpoint_data.get('portfolio', {})
                final_pnl = portfolio.get('realized_pnl', 0.0)
        
        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        
        return {
            "duration": self.session_metadata.get('duration', 0),
            "user_orders": user_orders,
            "executions": executions,
            "total_volume": total_volume,
            "average_spread": avg_spread,
            "active_strategies": list(active_strategies),
            "final_pnl": final_pnl,
            "event_count": len(self.events)
        }
    
    async def add_connection(self, websocket):
        """Add a WebSocket connection."""
        self.connections.add(websocket)
    
    async def remove_connection(self, websocket):
        """Remove a WebSocket connection."""
        self.connections.discard(websocket)
