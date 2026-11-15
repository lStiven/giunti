import { useEffect, useReducer, useRef, type ReactElement, type ReactNode } from "react";

import { ApiRequestError, extractQuestionnaire, fetchModels } from "./api/client";
import { ApiKeyStep } from "./components/ApiKeyStep";
import { ErrorNotice } from "./components/ErrorNotice";
import { FileDropzone } from "./components/FileDropzone";
import { AlertIcon } from "./components/icons";
import { ModelPicker } from "./components/ModelPicker";
import { MODE_LABELS, ModePicker } from "./components/ModePicker";
import { ProcessingView } from "./components/ProcessingView";
import { ResultView } from "./components/ResultView";
import { flowReducer, initialState, modelLabel, modelModes, type FlowState } from "./flow";
import { takeKeyFromUrl } from "./invite";
import { errorGuidance } from "./messages";
import { forgetApiKey, loadApiKey, saveApiKey } from "./storage";
import type { ReasoningMode } from "./types/questionnaire";

const AUTH_ERRORS = new Set(["UNAUTHENTICATED", "FORBIDDEN"]);

export default function App(): ReactElement {
  const [state, dispatch] = useReducer(flowReducer, null, () =>
    initialState(takeKeyFromUrl() ?? loadApiKey()),
  );
  const extraction = useRef<AbortController | null>(null);
  const { stage, apiKey } = state;

  useEffect(() => {
    if (stage !== "checkingKey" || apiKey === null) {
      return undefined;
    }
    const controller = new AbortController();
    fetchModels(apiKey, controller.signal).then(
      (catalog) => {
        saveApiKey(apiKey);
        dispatch({ type: "keyAccepted", catalog });
      },
      (error: unknown) => {
        const failure = asApiError(error);
        if (failure.code === "ABORTED") {
          return;
        }
        if (AUTH_ERRORS.has(failure.code)) {
          forgetApiKey();
          dispatch({ type: "keyRejected", error: failure });
        } else {
          dispatch({ type: "catalogFailed", error: failure });
        }
      },
    );
    return (): void => {
      controller.abort();
    };
  }, [stage, apiKey]);

  const extract = async (): Promise<void> => {
    if (state.file === null || apiKey === null) {
      return;
    }
    const controller = new AbortController();
    extraction.current = controller;
    dispatch({ type: "extractionStarted" });
    try {
      const result = await extractQuestionnaire({
        apiKey,
        file: state.file,
        model: state.model,
        mode: state.mode,
        signal: controller.signal,
      });
      dispatch({ type: "extractionSucceeded", result });
    } catch (error) {
      const failure = asApiError(error);
      if (failure.code === "ABORTED") {
        return;
      }
      if (AUTH_ERRORS.has(failure.code)) {
        forgetApiKey();
        dispatch({ type: "keyRejected", error: failure });
      } else {
        dispatch({ type: "extractionFailed", error: failure });
      }
    } finally {
      extraction.current = null;
    }
  };

  const cancel = (): void => {
    extraction.current?.abort();
    dispatch({ type: "extractionCancelled" });
  };

  return (
    <div className="page">
      <header className="hero">
        <p className="hero__eyebrow">PDF · Word · Excel → JSON</p>
        <h1 className="hero__title">Extrae las preguntas de tu cuestionario</h1>
        <p className="hero__lead">
          Sube una prueba o encuesta y obtén cada pregunta, sus alternativas y la respuesta
          correcta, listas para usar.
        </p>
      </header>
      <main className="panel">
        <Content state={state} dispatch={dispatch} onExtract={extract} onCancel={cancel} />
      </main>
      <footer className="footer">
        Los archivos se procesan y se descartan: no se guardan en el servidor.
      </footer>
    </div>
  );
}

interface ContentProps {
  state: FlowState;
  dispatch: (action: Parameters<typeof flowReducer>[1]) => void;
  onExtract: () => Promise<void>;
  onCancel: () => void;
}

function Content({ state, dispatch, onExtract, onCancel }: ContentProps): ReactElement {
  const fileName = state.file?.name ?? "";
  const model = state.model ?? "";

  switch (state.stage) {
    case "processing":
      return (
        <ProcessingView
          fileName={fileName}
          modelLabel={modelLabel(state.catalog, model)}
          onCancel={onCancel}
        />
      );
    case "done":
      return state.result ? (
        <ResultView
          result={state.result}
          fileName={fileName}
          modelLabel={withMode(
            modelLabel(state.catalog, state.result.run.model || model),
            state.result.run.mode,
          )}
          onTryAnotherModel={() => {
            dispatch({ type: "tryAnotherModel" });
          }}
          onStartOver={() => {
            dispatch({ type: "startOver" });
          }}
        />
      ) : (
        <></>
      );
    case "failed":
      return state.error ? (
        <ErrorNotice
          error={state.error}
          onRetry={() => void onExtract()}
          onStartOver={() => {
            dispatch({ type: "startOver" });
          }}
          onChangeModel={() => {
            dispatch({ type: "tryAnotherModel" });
          }}
          onReenterKey={() => {
            forgetApiKey();
            dispatch({ type: "keyChangeRequested" });
          }}
        />
      ) : (
        <></>
      );
    case "needsKey":
    case "checkingKey":
    case "unavailable":
    case "ready":
      return <SetupForm state={state} dispatch={dispatch} onExtract={onExtract} />;
  }
}

function SetupForm({ state, dispatch, onExtract }: Omit<ContentProps, "onCancel">): ReactElement {
  const keyAccepted = state.catalog !== null && state.stage !== "needsKey";
  const keyStage = keyAccepted
    ? "accepted"
    : state.stage === "checkingKey"
      ? "checkingKey"
      : "needsKey";
  const canExtract = state.stage === "ready" && state.file !== null && state.model !== null;

  return (
    <div className="setup">
      <ApiKeyStep
        stage={keyStage}
        error={state.stage === "needsKey" ? state.error : null}
        onSubmit={(apiKey) => {
          dispatch({ type: "keyChecking", apiKey });
        }}
        onChange={() => {
          dispatch({ type: "keyChangeRequested" });
        }}
      />

      {state.stage === "unavailable" && state.error && (
        <ServiceProblem
          error={state.error}
          onRetry={() => {
            dispatch({ type: "catalogRetried" });
          }}
        />
      )}

      {keyAccepted && state.catalog && (
        <>
          <Step number={2} title="Tu archivo">
            <FileDropzone
              file={state.file}
              disabled={false}
              onFile={(file) => {
                dispatch({ type: "fileChosen", file });
              }}
            />
          </Step>
          <Step number={3} title="El modelo que lo leerá">
            <ModelPicker
              catalog={state.catalog}
              selected={state.model}
              disabled={false}
              onSelect={(model) => {
                dispatch({ type: "modelChosen", model });
              }}
            />
            {modelModes(state.catalog, state.model).length > 1 && (
              <ModePicker
                selected={state.mode}
                disabled={false}
                onSelect={(mode) => {
                  dispatch({ type: "modeChosen", mode });
                }}
              />
            )}
          </Step>
          <div className="submit">
            <button
              type="button"
              className="button button--primary button--large"
              disabled={!canExtract}
              onClick={() => void onExtract()}
            >
              Extraer preguntas
            </button>
            {state.file === null && <p className="submit__hint">Elige un archivo para continuar</p>}
          </div>
        </>
      )}
    </div>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: ReactNode;
}): ReactElement {
  return (
    <section className="step step--enter" aria-label={title}>
      <span className="step__badge">{number}</span>
      <div className="step__body">
        <h2 className="step__title">{title}</h2>
        {children}
      </div>
    </section>
  );
}

function ServiceProblem({
  error,
  onRetry,
}: {
  error: ApiRequestError;
  onRetry: () => void;
}): ReactElement {
  const text = errorGuidance(error);
  return (
    <div className="notice notice--error" role="alert">
      <span className="notice__icon">
        <AlertIcon />
      </span>
      <div className="notice__body">
        <p className="notice__title">{text.title}</p>
        <p>{text.hint}</p>
        <button type="button" className="button button--ghost" onClick={onRetry}>
          Reintentar
        </button>
      </div>
    </div>
  );
}

function asApiError(error: unknown): ApiRequestError {
  if (error instanceof ApiRequestError) {
    return error;
  }
  return new ApiRequestError("UNKNOWN", error instanceof Error ? error.message : String(error));
}

function withMode(label: string, mode: ReasoningMode | null): string {
  return mode === null ? label : `${label} · ${MODE_LABELS[mode]}`;
}
