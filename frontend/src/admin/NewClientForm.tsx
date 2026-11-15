import { useId, useState, type ReactElement, type SubmitEvent } from "react";

import type { NewClient } from "./api";
import { PreciseModeCheck } from "./PreciseModeCheck";

interface NewClientFormProps {
  busy: boolean;
  onCreate: (client: NewClient) => void;
}

const DEFAULT_DAILY_LIMIT = 100;
const DEFAULT_PER_MINUTE_LIMIT = 10;

/** Name plus usage limits; the server derives the client id from the name. */
export function NewClientForm({ busy, onCreate }: NewClientFormProps): ReactElement {
  const [name, setName] = useState("");
  const [daily, setDaily] = useState(DEFAULT_DAILY_LIMIT);
  const [perMinute, setPerMinute] = useState(DEFAULT_PER_MINUTE_LIMIT);
  const [allowPrecise, setAllowPrecise] = useState(false);
  const id = useId();

  const submit = (event: SubmitEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (name.trim() === "") {
      return;
    }
    onCreate({
      name: name.trim(),
      daily_limit: daily,
      per_minute_limit: perMinute,
      allow_precise: allowPrecise,
    });
    setName("");
    setAllowPrecise(false);
  };

  return (
    <form className="new-client" onSubmit={submit}>
      <div className="field field--wide">
        <label htmlFor={`${id}-name`}>Nombre del cliente</label>
        <input
          id={`${id}-name`}
          className="input"
          placeholder="Por ejemplo: Colegio San José"
          maxLength={120}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-daily`}>Usos por día</label>
        <input
          id={`${id}-daily`}
          className="input"
          type="number"
          min={1}
          max={10000}
          value={daily}
          onChange={(event) => {
            setDaily(Number(event.target.value));
          }}
        />
      </div>
      <div className="field">
        <label htmlFor={`${id}-minute`}>Usos por minuto</label>
        <input
          id={`${id}-minute`}
          className="input"
          type="number"
          min={1}
          max={600}
          value={perMinute}
          onChange={(event) => {
            setPerMinute(Number(event.target.value));
          }}
        />
      </div>
      <button
        type="submit"
        className="button button--primary"
        disabled={busy || name.trim() === "" || daily < 1 || perMinute < 1}
      >
        {busy ? "Creando…" : "Crear invitación"}
      </button>
      <PreciseModeCheck
        className="new-client__check"
        checked={allowPrecise}
        onChange={setAllowPrecise}
      />
    </form>
  );
}
