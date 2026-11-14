import { useEffect, useRef, useState, type ReactElement } from "react";

import { waitingStage } from "../messages";

interface ProcessingViewProps {
  fileName: string;
  modelLabel: string;
  onCancel: () => void;
}

/**
 * Shown while the server works. The API reports no progress, so there is no fake percentage:
 * an animation, honest stage messages by elapsed time and the elapsed time itself.
 */
export function ProcessingView({
  fileName,
  modelLabel,
  onCancel,
}: ProcessingViewProps): ReactElement {
  const [elapsed, setElapsed] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return (): void => {
      window.clearInterval(timer);
    };
  }, []);

  return (
    <section className="processing" aria-labelledby="processing-title">
      <div className="scan" aria-hidden="true">
        <div className="scan__page">
          <span className="scan__line" />
          <span className="scan__line scan__line--short" />
          <span className="scan__line" />
          <span className="scan__line scan__line--mid" />
          <span className="scan__line" />
          <span className="scan__line scan__line--short" />
          <span className="scan__beam" />
        </div>
      </div>
      <h2 className="processing__title" id="processing-title" ref={heading} tabIndex={-1}>
        Extrayendo las preguntas
      </h2>
      <p className="processing__stage" aria-live="polite">
        {waitingStage(elapsed)}
      </p>
      <p className="processing__meta">
        <span className="processing__file">{fileName}</span> · {modelLabel}
      </p>
      <p className="processing__time">
        <span className="processing__clock">{formatClock(elapsed)}</span> · suele tardar entre 1 y 3
        minutos
      </p>
      <button type="button" className="button button--ghost" onClick={onCancel}>
        Cancelar
      </button>
    </section>
  );
}

function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes)}:${String(seconds % 60).padStart(2, "0")}`;
}
