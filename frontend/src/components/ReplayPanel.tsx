import React, { useState, useEffect, useCallback } from 'react';
import { Film, Circle, Square, Play, Pause, SkipBack, Rewind, FastForward, Clock, HardDrive } from 'lucide-react';
import { apiUrl } from '../config';

interface RecordingStatus {
  recording: boolean;
  filename: string | null;
  duration: number;
  event_count: number;
  file_size: number;
  warning: string | null;
}

interface ReplaySession {
  filename: string;
  size: number;
  modified: number;
  event_count: number;
  duration: number;
}

interface ReplayStatus {
  mode: 'stopped' | 'playing' | 'paused' | 'completed';
  loaded: boolean;
  session: any;
  current_index: number;
  total_events: number;
  progress: number;
  playback_speed: number;
  elapsed: number;
  current_event: any;
}

interface ReplayPanelProps {
  replayMode: boolean;
  onReplayModeChange: (enabled: boolean) => void;
}

export const ReplayPanel: React.FC<ReplayPanelProps> = ({ replayMode, onReplayModeChange }) => {
  const [activeMode, setActiveMode] = useState<'record' | 'replay'>('replay');
  
  // Recording state
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatus>({
    recording: false,
    filename: null,
    duration: 0,
    event_count: 0,
    file_size: 0,
    warning: null
  });
  const [sessionName, setSessionName] = useState('');
  
  // Replay state
  const [sessions, setSessions] = useState<ReplaySession[]>([]);
  const [replayStatus, setReplayStatus] = useState<ReplayStatus | null>(null);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  
  // Fetch recording status
  const fetchRecordingStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/recording/status'));
      const data = await res.json();
      setRecordingStatus(data);
    } catch (err) {
      console.error('Failed to fetch recording status:', err);
    }
  }, []);
  
  // Fetch replay status
  const fetchReplayStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/replay/status'));
      const data = await res.json();
      setReplayStatus(data);
    } catch (err) {
      console.error('Failed to fetch replay status:', err);
    }
  }, []);
  
  // Fetch available sessions
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/replay/sessions'));
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  }, []);
  
  // Poll statuses
  useEffect(() => {
    fetchRecordingStatus();
    fetchReplayStatus();
    fetchSessions();
    
    const interval = setInterval(() => {
      if (recordingStatus.recording) {
        fetchRecordingStatus();
      }
      if (replayStatus?.mode === 'playing') {
        fetchReplayStatus();
      }
    }, 500);
    
    return () => clearInterval(interval);
  }, [recordingStatus.recording, replayStatus?.mode]);
  
  // Recording controls
  const startRecording = async () => {
    try {
      const res = await fetch(apiUrl('/api/recording/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_name: sessionName || null })
      });
      if (res.ok) {
        fetchRecordingStatus();
        setSessionName('');
      }
    } catch (err) {
      console.error('Failed to start recording:', err);
    }
  };
  
  const stopRecording = async () => {
    try {
      await fetch(apiUrl('/api/recording/stop'), { method: 'POST' });
      fetchRecordingStatus();
      fetchSessions();
    } catch (err) {
      console.error('Failed to stop recording:', err);
    }
  };
  
  // Replay controls
  const loadSession = async (filename: string) => {
    try {
      const res = await fetch(apiUrl('/api/replay/load'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      if (res.ok) {
        setSelectedSession(filename);
        fetchReplayStatus();
        // Enter replay mode
        onReplayModeChange(true);
      }
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  };
  
  const playReplay = async () => {
    try {
      await fetch(apiUrl('/api/replay/play'), { method: 'POST' });
      fetchReplayStatus();
    } catch (err) {
      console.error('Failed to play replay:', err);
    }
  };
  
  const pauseReplay = async () => {
    try {
      await fetch(apiUrl('/api/replay/pause'), { method: 'POST' });
      fetchReplayStatus();
    } catch (err) {
      console.error('Failed to pause replay:', err);
    }
  };
  
  const stopReplay = async () => {
    try {
      await fetch(apiUrl('/api/replay/stop'), { method: 'POST' });
      fetchReplayStatus();
      // Exit replay mode
      onReplayModeChange(false);
    } catch (err) {
      console.error('Failed to stop replay:', err);
    }
  };
  
  const seekReplay = async (target: number) => {
    try {
      await fetch(apiUrl('/api/replay/seek'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target })
      });
      fetchReplayStatus();
    } catch (err) {
      console.error('Failed to seek:', err);
    }
  };
  
  const stepReplay = async (direction: number) => {
    try {
      await fetch(apiUrl('/api/replay/step'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction })
      });
      fetchReplayStatus();
    } catch (err) {
      console.error('Failed to step:', err);
    }
  };
  
  const setSpeed = async (speed: number) => {
    try {
      await fetch(apiUrl('/api/replay/speed'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed })
      });
      fetchReplayStatus();
    } catch (err) {
      console.error('Failed to set speed:', err);
    }
  };
  
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };
  
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', padding: '12px', overflow: 'auto' }}>
      {/* Replay Mode Banner */}
      {replayMode && (
        <div style={{
          padding: '10px 14px',
          background: 'rgba(255, 149, 0, 0.15)',
          border: '1px solid var(--replay-orange)',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--replay-orange)' }} />
            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--replay-orange)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Replay Mode Active
            </span>
          </div>
          <button 
            onClick={() => { stopReplay(); onReplayModeChange(false); }} 
            className="btn btn-secondary"
            style={{ fontSize: '10px', padding: '4px 10px' }}
          >
            Exit Replay
          </button>
        </div>
      )}
      
      {/* Mode Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '8px' }}>
        <button
          onClick={() => setActiveMode('replay')}
          className={`btn ${activeMode === 'replay' ? '' : 'btn-secondary'}`}
          style={{ flex: 1, fontSize: '11px', padding: '6px 12px' }}
          disabled={replayMode}
        >
          <Play size={12} /> Replay
        </button>
        <button
          onClick={() => setActiveMode('record')}
          className={`btn ${activeMode === 'record' ? '' : 'btn-secondary'}`}
          style={{ flex: 1, fontSize: '11px', padding: '6px 12px' }}
          disabled={replayMode}
        >
          <Circle size={12} /> Record
        </button>
      </div>

      {/* Recording Panel */}
      {activeMode === 'record' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div className="terminal-panel" style={{ padding: '12px' }}>
            <h4 style={{ fontSize: '11px', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Session Recording
            </h4>
            
            {!recordingStatus.recording ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="Session name (optional)"
                  value={sessionName}
                  onChange={(e) => setSessionName(e.target.value)}
                  style={{ fontSize: '11px', padding: '6px 8px' }}
                />
                <button className="btn btn-sell" onClick={startRecording} style={{ fontSize: '11px', padding: '8px 12px' }}>
                  <Circle size={14} fill="var(--sell-red)" /> Start Recording
                </button>
                <p style={{ fontSize: '9px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Records all market events, orders, trades, and strategy activity for later replay.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px', background: 'var(--bg-input)', borderRadius: '4px' }}>
                  <Circle size={12} fill="var(--sell-red)" className="pulse" />
                  <span style={{ fontSize: '11px', fontWeight: 600 }}>RECORDING</span>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '10px' }}>
                  <div>
                    <div style={{ color: 'var(--text-dim)' }}>Duration</div>
                    <div className="mono" style={{ fontWeight: 600 }}>{formatDuration(recordingStatus.duration)}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-dim)' }}>Events</div>
                    <div className="mono" style={{ fontWeight: 600 }}>{recordingStatus.event_count.toLocaleString()}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-dim)' }}>File Size</div>
                    <div className="mono" style={{ fontWeight: 600 }}>{formatFileSize(recordingStatus.file_size)}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-dim)' }}>Filename</div>
                    <div className="mono" style={{ fontWeight: 600, fontSize: '9px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {recordingStatus.filename?.substring(0, 20)}
                    </div>
                  </div>
                </div>
                
                {recordingStatus.warning && (
                  <div style={{ padding: '6px 8px', background: 'rgba(255, 165, 0, 0.1)', border: '1px solid var(--sell-red)', borderRadius: '4px', fontSize: '10px', color: 'var(--sell-red)' }}>
                    ⚠ {recordingStatus.warning}
                  </div>
                )}
                
                <button className="btn" onClick={stopRecording} style={{ fontSize: '11px', padding: '8px 12px', marginTop: '4px' }}>
                  <Square size={14} /> Stop Recording
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Replay Panel */}
      {activeMode === 'replay' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Playback Controls */}
          {replayStatus?.loaded && (
            <div className="terminal-panel" style={{ padding: '12px' }}>
              <h4 style={{ fontSize: '11px', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Playback Controls
              </h4>
              
              {replayStatus.mode === 'completed' && (
                <div style={{
                  padding: '8px 10px',
                  marginBottom: '10px',
                  background: 'rgba(0, 230, 118, 0.1)',
                  border: '1px solid var(--buy-green)',
                  borderRadius: '4px',
                  fontSize: '10px',
                  fontWeight: 600,
                  color: 'var(--buy-green)',
                  textAlign: 'center'
                }}>
                  ✓ Replay Finished — click Play to watch again, or Exit Replay to return to Live
                </div>
              )}
              
              {/* Timeline Slider */}
              <div style={{ marginBottom: '12px' }}>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.001"
                  value={replayStatus.progress}
                  onChange={(e) => seekReplay(parseFloat(e.target.value))}
                  style={{ width: '100%', height: '8px', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  <span>{formatDuration(replayStatus.elapsed)}</span>
                  <span>{replayStatus.current_index} / {replayStatus.total_events} events</span>
                  <span>{formatDuration(replayStatus.session?.duration || 0)}</span>
                </div>
              </div>
              
              {/* Control Buttons */}
              <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                <button className="btn btn-secondary" onClick={stopReplay} style={{ fontSize: '10px', padding: '6px 10px' }} title="Restart">
                  <SkipBack size={14} />
                </button>
                <button className="btn btn-secondary" onClick={() => stepReplay(-1)} style={{ fontSize: '10px', padding: '6px 10px' }} title="Previous Event">
                  <Rewind size={14} />
                </button>
                
                {replayStatus.mode !== 'playing' ? (
                  <button className="btn btn-buy" onClick={playReplay} style={{ flex: 1, fontSize: '11px', padding: '8px 12px' }}>
                    <Play size={14} /> {replayStatus.mode === 'paused' ? 'Resume' : replayStatus.mode === 'completed' ? 'Replay Again' : 'Play'}
                  </button>
                ) : (
                  <button className="btn" onClick={pauseReplay} style={{ flex: 1, fontSize: '11px', padding: '8px 12px' }}>
                    <Pause size={14} /> Pause
                  </button>
                )}
                
                <button className="btn btn-secondary" onClick={() => stepReplay(1)} style={{ fontSize: '10px', padding: '6px 10px' }} title="Next Event">
                  <FastForward size={14} />
                </button>
              </div>
              
              {/* Speed Controls */}
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                <span style={{ fontSize: '10px', color: 'var(--text-dim)', marginRight: '4px' }}>Speed:</span>
                {[0.25, 0.5, 1, 2, 5].map(speed => (
                  <button
                    key={speed}
                    className={`btn ${replayStatus.playback_speed === speed ? '' : 'btn-secondary'}`}
                    onClick={() => setSpeed(speed)}
                    style={{ fontSize: '9px', padding: '4px 8px', flex: 1 }}
                  >
                    {speed}x
                  </button>
                ))}
              </div>
              
              {/* Status */}
              <div style={{ marginTop: '8px', padding: '6px 8px', background: 'var(--bg-input)', borderRadius: '4px', fontSize: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Status:</span>
                  <span style={{ fontWeight: 600, textTransform: 'uppercase', color: (replayStatus.mode === 'playing' || replayStatus.mode === 'completed') ? 'var(--buy-green)' : 'var(--text-main)' }}>
                    {replayStatus.mode}
                  </span>
                </div>
                {replayStatus.current_event && (
                  <div style={{ fontSize: '9px', color: 'var(--text-dim)', marginTop: '4px' }}>
                    Current: {replayStatus.current_event.type}
                  </div>
                )}
              </div>
            </div>
          )}
          
          {/* Session Browser */}
          <div className="terminal-panel" style={{ padding: '12px' }}>
            <h4 style={{ fontSize: '11px', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Session Library ({sessions.length})
            </h4>
            
            {sessions.length === 0 ? (
              <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '10px' }}>
                No recorded sessions yet. Start a recording to create one.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '300px', overflowY: 'auto' }}>
                {sessions.map((session) => (
                  <div
                    key={session.filename}
                    onClick={() => loadSession(session.filename)}
                    style={{
                      padding: '8px 10px',
                      background: selectedSession === session.filename ? 'var(--accent-cyan-dim)' : 'var(--bg-input)',
                      border: `1px solid ${selectedSession === session.filename ? 'var(--accent-cyan)' : 'var(--border-color)'}`,
                      borderRadius: '4px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                    onMouseEnter={(e) => { if (selectedSession !== session.filename) e.currentTarget.style.background = 'rgba(255,255,255,0.03)' }}
                    onMouseLeave={(e) => { if (selectedSession !== session.filename) e.currentTarget.style.background = 'var(--bg-input)' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <Film size={12} color="var(--accent-cyan)" />
                      <span style={{ fontSize: '10px', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {session.filename}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', fontSize: '9px', color: 'var(--text-dim)' }}>
                      <span><Clock size={10} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> {formatDuration(session.duration)}</span>
                      <span><HardDrive size={10} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> {formatFileSize(session.size)}</span>
                      <span>{session.event_count.toLocaleString()} events</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
