import { useEffect, useRef, useState, type ReactElement } from "react";

import { formatDuration, languageName, noticeText } from "../messages";
import type { ExtractionResult } from "../types/questionnaire";
import { CopyIcon, DownloadIcon, SparkIcon } from "./icons";
import { ItemCard } from "./ItemCard";

interface ResultViewProps {
  result: ExtractionResult;
  modelLabel: string;
  fileName: string;
  onTryAnotherModel: () => void;
  onStartOver: () => void;
}

type View = "items" | "json";
type CopyState = "idle" | "copied" | "failed";

export function ResultView({
  result,
  modelLabel,
  fileName,
  onTryAnotherModel,
  onStartOver,
}: ResultViewProps): ReactElement {
  const { questionnaire, run } = result;
  const [view, setView] = useState<View>("items");
  const [copy, setCopy] = useState<CopyState>("idle");
  const heading = useRef<HTMLHeadingElement>(null);
  const json = JSON.stringify(questionnaire, null, 2);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  useEffect(() => {
    if (copy === "idle") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setCopy("idle");
    }, 2500);
    return (): void => {
      window.clearTimeout(timer);
    };
  }, [copy]);

  const copyJson = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(json);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };

  return (
    <section className="result" aria-labelledby="result-title">
      <header className="result__header">
        <span className="result__spark">
          <SparkIcon />
        </span>
        <div>
          <h2 className="result__title" id="result-title" ref={heading} tabIndex={-1}>
            {questionnaire.total_items === 1
              ? "Encontramos 1 pregunta"
              : `Encontramos ${String(questionnaire.total_items)} preguntas`}
          </h2>
          <p className="result__subtitle">{questionnaire.titulo ?? fileName}</p>
        </div>
      </header>

      <dl className="stats">
        <div className="stats__item">
          <dt>Idioma</dt>
          <dd>{languageName(questionnaire.idioma)}</dd>
        </div>
        <div className="stats__item">
          <dt>Modelo</dt>
          <dd>{modelLabel}</dd>
        </div>
        <div className="stats__item">
          <dt>Tiempo</dt>
          <dd>{formatDuration(run.durationMs)}</dd>
        </div>
        {run.dailyRemaining !== null && (
          <div className="stats__item">
            <dt>Te quedan hoy</dt>
            <dd>{run.dailyRemaining}</dd>
          </div>
        )}
      </dl>

      {run.notices.length > 0 && (
        <details className="notice notice--warning">
          <summary>
            {run.notices.length === 1
              ? "1 aviso: revisa este punto"
              : `${String(run.notices.length)} avisos: revisa estos puntos`}
          </summary>
          <ul className="notice__list">
            {run.notices.map((notice) => (
              <li key={`${notice.code}:${notice.message}`}>{noticeText(notice)}</li>
            ))}
          </ul>
        </details>
      )}

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Formato del resultado">
          <button
            type="button"
            className="segmented__option"
            aria-pressed={view === "items"}
            onClick={() => {
              setView("items");
            }}
          >
            Preguntas
          </button>
          <button
            type="button"
            className="segmented__option"
            aria-pressed={view === "json"}
            onClick={() => {
              setView("json");
            }}
          >
            JSON
          </button>
        </div>
        <div className="toolbar__actions">
          <button type="button" className="button button--ghost" onClick={() => void copyJson()}>
            <CopyIcon /> {copy === "copied" ? "¡Copiado!" : "Copiar JSON"}
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => {
              downloadJson(json, fileName);
            }}
          >
            <DownloadIcon /> Descargar
          </button>
        </div>
      </div>
      <p className="visually-hidden" aria-live="polite">
        {copy === "copied" ? "JSON copiado al portapapeles" : ""}
        {copy === "failed" ? "No se pudo copiar el JSON" : ""}
      </p>

      {view === "items" ? (
        <ol className="items">
          {questionnaire.items.map((item, index) => (
            <ItemCard key={item.numero} item={item} index={index} />
          ))}
        </ol>
      ) : (
        <pre className="json" aria-label="Resultado en JSON">
          {json}
        </pre>
      )}

      <div className="actions actions--center">
        <button type="button" className="button button--ghost" onClick={onTryAnotherModel}>
          Probar con otro modelo
        </button>
        <button type="button" className="button" onClick={onStartOver}>
          Procesar otro archivo
        </button>
      </div>
    </section>
  );
}

function downloadJson(json: string, fileName: string): void {
  const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${fileName.replace(/\.[^.]+$/, "")}.json`;
  link.click();
  URL.revokeObjectURL(url);
}
