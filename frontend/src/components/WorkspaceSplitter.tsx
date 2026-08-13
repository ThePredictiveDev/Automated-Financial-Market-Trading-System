import { useCallback, useRef, useState } from 'react';

interface WorkspaceSplitterProps {
  onDrag: (clientY: number) => void;
  onDragEnd: () => void;
  dockHeight: number;
  minDock: number;
  maxDock: number;
}

export function WorkspaceSplitter({
  onDrag,
  onDragEnd,
  dockHeight,
  minDock,
  maxDock,
}: WorkspaceSplitterProps) {
  const [active, setActive] = useState(false);
  const dragging = useRef(false);

  const stopDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    setActive(false);
    document.body.classList.remove('is-ns-resizing');
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* capture may already be released */
    }
    onDragEnd();
  }, [onDragEnd]);

  return (
    <div
      className={`workspace-splitter${active ? ' is-active' : ''}`}
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize trading workspace and lower panels"
      aria-valuemin={Math.round(minDock)}
      aria-valuemax={Math.round(maxDock)}
      aria-valuenow={Math.round(dockHeight)}
      tabIndex={0}
      onPointerDown={(event) => {
        if (event.button !== 0 && event.pointerType === 'mouse') return;
        dragging.current = true;
        setActive(true);
        document.body.classList.add('is-ns-resizing');
        event.currentTarget.setPointerCapture(event.pointerId);
        event.preventDefault();
        onDrag(event.clientY);
      }}
      onPointerMove={(event) => {
        if (!dragging.current) return;
        onDrag(event.clientY);
      }}
      onPointerUp={stopDrag}
      onPointerCancel={stopDrag}
    />
  );
}
