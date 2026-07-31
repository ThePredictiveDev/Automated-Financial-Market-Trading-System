"""
Event-based recording of trading sessions for deterministic replay.

Records individual events (orders, executions, price updates, strategy toggles)
with periodic state checkpoints to enable efficient replay without storing
complete market snapshots every tick.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ReplayRecorder:
    """
    Records trading session events to JSON Lines format for later replay.
    
    Event-based recording with periodic state checkpoints ensures:
    - Efficient storage (no redundant full snapshots every tick)
    - Complete session reconstruction (events + checkpoints)
    - Streamable playback (process line-by-line)
    """
    
    def __init__(self, sessions_dir: str = "replay_sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        self.is_recording = False
        self.session_file: Optional[Path] = None
        self.file_handle: Optional[Any] = None
        self.event_count = 0
        self.session_start_time: Optional[float] = None
        self.last_checkpoint_time: Optional[float] = None
        # Checkpoints are full state snapshots (order book, chart history,
        # portfolio, user orders, strategy states). A short interval keeps
        # replay fidelity high (order book / portfolio never drift far from
        # reality) without meaningfully bloating file size for a simulator
        # with a handful of symbols and shallow book depth.
        self.checkpoint_interval = 5.0  # Checkpoint every 5 seconds
        
    def start_recording(self, session_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Start a new recording session.
        
        Args:
            session_name: Optional custom name (default: timestamp-based)
            
        Returns:
            Session metadata (filename, start_time, etc.)
        """
        if self.is_recording:
            raise RuntimeError("Recording already in progress")
        
        # Generate filename
        if session_name:
            # Sanitize custom name
            safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in session_name)
            filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        else:
            filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        
        self.session_file = self.sessions_dir / filename
        self.file_handle = open(self.session_file, 'w', encoding='utf-8')
        self.event_count = 0
        self.session_start_time = time.time()
        self.last_checkpoint_time = self.session_start_time
        self.is_recording = True
        
        logger.info(f"Started recording session: {self.session_file}")
        
        return {
            "filename": str(self.session_file.name),
            "start_time": self.session_start_time,
            "status": "recording"
        }
    
    def stop_recording(self) -> Dict[str, Any]:
        """
        Stop the current recording session.
        
        Returns:
            Session summary (filename, duration, event_count, file_size)
        """
        if not self.is_recording:
            raise RuntimeError("No recording in progress")
        
        # Write session end marker
        self._write_event({
            "type": "SESSION_END",
            "data": {
                "duration": time.time() - self.session_start_time if self.session_start_time else 0,
                "total_events": self.event_count
            }
        })
        
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
        
        file_size = self.session_file.stat().st_size if self.session_file else 0
        duration = time.time() - self.session_start_time if self.session_start_time else 0
        
        summary = {
            "filename": str(self.session_file.name) if self.session_file else None,
            "duration": duration,
            "event_count": self.event_count,
            "file_size": file_size,
            "status": "completed"
        }
        
        logger.info(f"Stopped recording: {self.event_count} events, {duration:.1f}s, {file_size/1024:.1f}KB")
        
        self.is_recording = False
        self.session_file = None
        self.event_count = 0
        self.session_start_time = None
        self.last_checkpoint_time = None
        
        return summary
    
    def record_session_start(self, initial_state: Dict[str, Any]) -> None:
        """Record SESSION_START event with initial configuration."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "SESSION_START",
            "data": initial_state
        })
    
    def record_tick(self, symbol: str, price: float) -> None:
        """Record TICK event (market price update)."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "TICK",
            "data": {
                "symbol": symbol,
                "price": price
            }
        })
    
    def record_lifecycle(self, stage: str, order_id: Optional[str] = None, 
                        symbol: Optional[str] = None, details: Optional[str] = None,
                        **kwargs) -> None:
        """Record LIFECYCLE event (order lifecycle stages)."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "LIFECYCLE",
            "data": {
                "stage": stage,
                "order_id": order_id,
                "symbol": symbol,
                "details": details,
                **kwargs
            }
        })
    
    def record_trade(self, trade_data: Dict[str, Any]) -> None:
        """Record TRADE event (execution)."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "TRADE",
            "data": trade_data
        })
    
    def record_strategy_toggle(self, strategy_name: str, enabled: bool) -> None:
        """Record STRATEGY_TOGGLE event."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "STRATEGY_TOGGLE",
            "data": {
                "strategy": strategy_name,
                "enabled": enabled
            }
        })
    
    def record_user_order(self, order_data: Dict[str, Any]) -> None:
        """Record USER_ORDER event."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "USER_ORDER",
            "data": order_data
        })
    
    def record_user_cancel(self, order_id: str, symbol: str) -> None:
        """Record USER_CANCEL event."""
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "USER_CANCEL",
            "data": {
                "order_id": order_id,
                "symbol": symbol
            }
        })
    
    def record_checkpoint(self, state_snapshot: Dict[str, Any]) -> None:
        """
        Record CHECKPOINT event (periodic full state snapshot).
        
        Checkpoints enable efficient replay - instead of replaying from the
        beginning, replay can start from the nearest checkpoint.
        """
        if not self.is_recording:
            return
        
        self._write_event({
            "type": "CHECKPOINT",
            "data": state_snapshot
        })
        
        self.last_checkpoint_time = time.time()
    
    def should_checkpoint(self) -> bool:
        """Check if it's time for a periodic checkpoint."""
        if not self.is_recording or not self.last_checkpoint_time:
            return False
        
        return (time.time() - self.last_checkpoint_time) >= self.checkpoint_interval
    
    def get_status(self) -> Dict[str, Any]:
        """Get current recording status."""
        if not self.is_recording:
            return {
                "recording": False,
                "filename": None,
                "duration": 0,
                "event_count": 0,
                "file_size": 0
            }
        
        duration = time.time() - self.session_start_time if self.session_start_time else 0
        file_size = self.session_file.stat().st_size if self.session_file and self.session_file.exists() else 0
        
        return {
            "recording": True,
            "filename": str(self.session_file.name) if self.session_file else None,
            "duration": duration,
            "event_count": self.event_count,
            "file_size": file_size,
            "warning": "Long recording (>15 min)" if duration > 900 else None
        }
    
    def _write_event(self, event: Dict[str, Any]) -> None:
        """Write a single event to the recording file."""
        if not self.file_handle:
            return
        
        # Add sequence number and timestamp
        full_event = {
            "seq": self.event_count,
            "ts": time.time(),
            **event
        }
        
        try:
            self.file_handle.write(json.dumps(full_event) + '\n')
            self.file_handle.flush()  # Ensure immediate write for safety
            self.event_count += 1
        except Exception as e:
            logger.error(f"Failed to write event: {e}", exc_info=True)
    
    @staticmethod
    def list_sessions(sessions_dir: str = "replay_sessions") -> list[Dict[str, Any]]:
        """List all available session files with metadata."""
        sessions_path = Path(sessions_dir)
        if not sessions_path.exists():
            return []
        
        sessions = []
        for file_path in sorted(sessions_path.glob("*.jsonl"), reverse=True):
            try:
                stat = file_path.stat()
                
                # Quick scan to get event count and duration
                event_count = 0
                duration = 0.0
                start_ts = None
                end_ts = None
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        event_count += 1
                        try:
                            event = json.loads(line)
                            if event_count == 1:
                                start_ts = event.get('ts')
                            end_ts = event.get('ts')
                        except:
                            pass
                
                if start_ts and end_ts:
                    duration = end_ts - start_ts
                
                sessions.append({
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "event_count": event_count,
                    "duration": duration
                })
            except Exception as e:
                logger.warning(f"Failed to read session {file_path}: {e}")
        
        return sessions
