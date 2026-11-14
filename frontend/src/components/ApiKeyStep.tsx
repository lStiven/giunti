import { useId, type ReactElement } from "react";

import type { ApiRequestError } from "../api/client";
import { errorText } from "../messages";
import { CheckIcon } from "./icons";
import { KeyLogin } from "./KeyLogin";

interface ApiKeyStepProps {
  stage: "needsKey" | "checkingKey" | "accepted";
  error: ApiRequestError | null;
  onSubmit: (apiKey: string) => void;
  onChange: () => void;
}

/** Step 1: the client's access key. Once accepted it collapses into a one-line summary. */
export function ApiKeyStep({ stage, error, onSubmit, onChange }: ApiKeyStepProps): ReactElement {
  const titleId = useId();

  if (stage === "accepted") {
    return (
      <section className="step step--done" aria-label="Clave de acceso">
        <span className="step__badge step__badge--done">
          <CheckIcon />
        </span>
        <p className="step__summary">Clave de acceso guardada en este navegador</p>
        <button type="button" className="link-button" onClick={onChange}>
          Cambiar
        </button>
      </section>
    );
  }

  const problem = error ? errorText(error.code) : null;
  return (
    <section className="step" aria-labelledby={titleId}>
      <span className="step__badge">1</span>
      <div className="step__body">
        <h2 className="step__title" id={titleId}>
          Tu clave de acceso
        </h2>
        <p className="step__help">
          Si recibiste un enlace de invitación, ábrelo y entrarás directo. Si no, pega aquí la clave
          que te dio el administrador.
        </p>
        <KeyLogin
          label="Clave de acceso"
          checking={stage === "checkingKey"}
          problem={problem ? `${problem.title}. ${problem.hint}` : null}
          onSubmit={onSubmit}
        />
      </div>
    </section>
  );
}
