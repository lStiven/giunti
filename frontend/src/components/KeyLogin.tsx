import { useId, useState, type ReactElement, type SubmitEvent } from "react";

import { KeyIcon } from "./icons";

interface KeyLoginProps {
  label: string;
  checking: boolean;
  /** Already-translated problem to show under the field. */
  problem: string | null;
  onSubmit: (key: string) => void;
}

/** A password-style field and button to enter an access key. */
export function KeyLogin({ label, checking, problem, onSubmit }: KeyLoginProps): ReactElement {
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const errorId = useId();

  const handleSubmit = (event: SubmitEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const key = draft.trim();
    if (key !== "") {
      onSubmit(key);
    }
  };

  return (
    <>
      <form className="key-form" onSubmit={handleSubmit}>
        <div className="key-form__field">
          <KeyIcon />
          <label className="visually-hidden" htmlFor={inputId}>
            {label}
          </label>
          <input
            id={inputId}
            className="key-form__input"
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="gk_…"
            value={draft}
            disabled={checking}
            aria-invalid={problem !== null}
            aria-describedby={problem ? errorId : undefined}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
        </div>
        <button
          type="submit"
          className="button button--secondary"
          disabled={checking || draft.trim() === ""}
        >
          {checking ? "Comprobando…" : "Continuar"}
        </button>
      </form>
      {problem && (
        <p className="field-error" id={errorId} role="alert">
          {problem}
        </p>
      )}
    </>
  );
}
