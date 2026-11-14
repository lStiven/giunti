import { useEffect, useRef, useState, type ReactElement } from "react";

import type { ApiRequestError } from "../api/client";
import { errorGuidance, formatWait, type ErrorAction } from "../messages";
import { CopyButton } from "./CopyButton";
import { AlertIcon, ChangeFileIcon, KeyIcon, ModelIcon, RetryIcon, WaitIcon } from "./icons";

interface ErrorNoticeProps {
  error: ApiRequestError;
  onRetry: () => void;
  onStartOver: () => void;
  onChangeModel: () => void;
  onReenterKey: () => void;
}

/** Seconds left until `seconds` from the first render; ticks once per second. */
function useCountdown(seconds: number | null): number {
  const [left, setLeft] = useState(seconds ?? 0);
  useEffect(() => {
    if (seconds === null || seconds <= 0) {
      return undefined;
    }
    const deadline = Date.now() + seconds * 1000;
    const timer = window.setInterval(() => {
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setLeft(remaining);
      if (remaining === 0) {
        window.clearInterval(timer);
      }
    }, 1000);
    return (): void => {
      window.clearInterval(timer);
    };
  }, [seconds]);
  return left;
}

/** A failed extraction: what happened, what to do next, and the details for support. */
export function ErrorNotice({
  error,
  onRetry,
  onStartOver,
  onChangeModel,
  onReenterKey,
}: ErrorNoticeProps): ReactElement {
  const heading = useRef<HTMLHeadingElement>(null);
  const guidance = errorGuidance(error);
  const waits = guidance.actions.includes("wait") && error.retryAfterSeconds !== null;
  const secondsLeft = useCountdown(waits ? error.retryAfterSeconds : null);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  const labels: Record<ErrorAction, string | null> = {
    retry: "Intentar de nuevo",
    wait: secondsLeft > 0 ? `Podrás reintentar en ${formatWait(secondsLeft)}` : "Intentar de nuevo",
    changeModel: "Elegir otro modelo",
    changeFile: "Elegir otro archivo",
    reenterKey: "Ingresar otra clave",
    contactAdmin: null,
  };
  const icons: Record<ErrorAction, ReactElement | null> = {
    retry: <RetryIcon />,
    wait: secondsLeft > 0 ? <WaitIcon /> : <RetryIcon />,
    changeModel: <ModelIcon />,
    changeFile: <ChangeFileIcon />,
    reenterKey: <KeyIcon />,
    contactAdmin: null,
  };
  const handlers: Record<ErrorAction, () => void> = {
    retry: onRetry,
    wait: onRetry,
    changeModel: onChangeModel,
    changeFile: onStartOver,
    reenterKey: onReenterKey,
    contactAdmin: onRetry,
  };
  const shown = guidance.actions.filter((action) => labels[action] !== null);
  if (!shown.includes("changeFile")) {
    shown.push("changeFile");
  }

  return (
    <section className="notice notice--error" aria-labelledby="error-title">
      <span className="notice__icon">
        <AlertIcon />
      </span>
      <div className="notice__body">
        <h2 className="notice__title" id="error-title" ref={heading} tabIndex={-1}>
          {guidance.title}
        </h2>
        <p>{guidance.hint}</p>
        {guidance.actions.includes("contactAdmin") && error.requestId && (
          <p className="notice__support">
            Si se repite, comparte este código con el administrador: <code>{error.requestId}</code>{" "}
            <CopyButton
              text={error.requestId}
              label="Copiar código"
              className="button button--ghost button--small"
            />
          </p>
        )}
        <details className="notice__details">
          <summary>Detalle técnico</summary>
          <p>
            {error.code}
            {error.reason ? ` (${error.reason})` : ""}: {error.message}
          </p>
          {error.requestId && <p>Código de solicitud: {error.requestId}</p>}
        </details>
        <div className="actions">
          {shown.map((action, index) => (
            <button
              key={action}
              type="button"
              className={index === 0 ? "button" : "button button--ghost"}
              onClick={handlers[action]}
              disabled={action === "wait" && secondsLeft > 0}
            >
              {icons[action]}
              {labels[action]}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
