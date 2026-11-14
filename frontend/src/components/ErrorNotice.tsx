import { useEffect, useRef, type ReactElement } from "react";

import type { ApiRequestError } from "../api/client";
import { errorText } from "../messages";
import { AlertIcon } from "./icons";

/** Errors caused by the file itself: retrying the same file cannot help. */
const FILE_ERROR_CODES = new Set([
  "UNSUPPORTED_FORMAT",
  "INVALID_FILE",
  "EMPTY_FILE",
  "FILE_TOO_LARGE",
  "PROTECTED_FILE",
  "NO_TEXT",
]);

interface ErrorNoticeProps {
  error: ApiRequestError;
  onRetry: () => void;
  onStartOver: () => void;
}

/** A failed extraction: what happened, what to do, and the technical detail for support. */
export function ErrorNotice({ error, onRetry, onStartOver }: ErrorNoticeProps): ReactElement {
  const heading = useRef<HTMLHeadingElement>(null);
  const text = errorText(error.code, error.retryAfterSeconds);
  const fileProblem = FILE_ERROR_CODES.has(error.code);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <section className="notice notice--error" aria-labelledby="error-title">
      <span className="notice__icon">
        <AlertIcon />
      </span>
      <div className="notice__body">
        <h2 className="notice__title" id="error-title" ref={heading} tabIndex={-1}>
          {text.title}
        </h2>
        <p>{text.hint}</p>
        <details className="notice__details">
          <summary>Detalle técnico</summary>
          <p>
            {error.code}: {error.message}
          </p>
          {error.requestId && <p>Código de solicitud: {error.requestId}</p>}
        </details>
        <div className="actions">
          {!fileProblem && (
            <button type="button" className="button" onClick={onRetry}>
              Intentar de nuevo
            </button>
          )}
          <button
            type="button"
            className={fileProblem ? "button" : "button button--ghost"}
            onClick={onStartOver}
          >
            Elegir otro archivo
          </button>
        </div>
      </div>
    </section>
  );
}
