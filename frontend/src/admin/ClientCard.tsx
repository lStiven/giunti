import { useId, useState, type ReactElement, type SubmitEvent } from "react";

import type { ClientChanges, ClientView } from "./api";
import { PreciseModeCheck } from "./PreciseModeCheck";

interface ClientCardProps {
  client: ClientView;
  busy: boolean;
  onChange: (changes: ClientChanges) => void;
  onNewInvitation: () => void;
  onDelete: () => void;
}

const DATE_FORMAT = new Intl.DateTimeFormat("es", { dateStyle: "short", timeStyle: "short" });

/** One client: status, today's usage and the actions an administrator can take. */
export function ClientCard({
  client,
  busy,
  onChange,
  onNewInvitation,
  onDelete,
}: ClientCardProps): ReactElement {
  const [editing, setEditing] = useState(false);

  return (
    <li className={`client-card${client.active ? "" : " client-card--inactive"}`}>
      <div className="client-card__header">
        <div>
          <p className="client-card__name">{client.name}</p>
          <p className="client-card__id">{client.id}</p>
        </div>
        <span className="client-card__tags">
          {client.is_admin && <span className="tag tag--accent">Administrador</span>}
          <span className={client.active ? "tag tag--success" : "tag tag--warning"}>
            {client.active ? "Activo" : "Desactivado"}
          </span>
          <span className="tag">{client.allow_precise ? "Rápido y preciso" : "Solo rápido"}</span>
        </span>
      </div>

      <dl className="client-card__stats">
        <div>
          <dt>Hoy</dt>
          <dd>
            {client.used_today} de {client.daily_limit}
          </dd>
        </div>
        <div>
          <dt>Por minuto</dt>
          <dd>{client.per_minute_limit}</dd>
        </div>
        <div>
          <dt>Último uso</dt>
          <dd>
            {client.last_used_at ? DATE_FORMAT.format(new Date(client.last_used_at)) : "Nunca"}
          </dd>
        </div>
      </dl>

      {client.is_admin ? (
        <p className="client-card__note">Los administradores se gestionan desde la terminal.</p>
      ) : editing ? (
        <LimitsForm
          client={client}
          busy={busy}
          onSave={(changes) => {
            onChange(changes);
            setEditing(false);
          }}
          onCancel={() => {
            setEditing(false);
          }}
        />
      ) : (
        <div className="client-card__actions">
          <button
            type="button"
            className="button button--ghost button--small"
            disabled={busy}
            onClick={() => {
              onChange({ active: !client.active });
            }}
          >
            {client.active ? "Desactivar" : "Activar"}
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            disabled={busy}
            onClick={() => {
              setEditing(true);
            }}
          >
            Editar acceso
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            disabled={busy}
            onClick={onNewInvitation}
          >
            Nueva invitación
          </button>
          <button
            type="button"
            className="button button--danger button--small"
            disabled={busy}
            onClick={onDelete}
          >
            Eliminar
          </button>
        </div>
      )}
    </li>
  );
}

function LimitsForm({
  client,
  busy,
  onSave,
  onCancel,
}: {
  client: ClientView;
  busy: boolean;
  onSave: (changes: ClientChanges) => void;
  onCancel: () => void;
}): ReactElement {
  const [daily, setDaily] = useState(client.daily_limit);
  const [perMinute, setPerMinute] = useState(client.per_minute_limit);
  const [allowPrecise, setAllowPrecise] = useState(client.allow_precise);
  const id = useId();

  const submit = (event: SubmitEvent<HTMLFormElement>): void => {
    event.preventDefault();
    onSave({ daily_limit: daily, per_minute_limit: perMinute, allow_precise: allowPrecise });
  };

  return (
    <form className="limits-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor={`${id}-daily`}>Por día</label>
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
        <label htmlFor={`${id}-minute`}>Por minuto</label>
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
      <PreciseModeCheck
        className="limits-form__check"
        checked={allowPrecise}
        onChange={setAllowPrecise}
      />
      <div className="limits-form__actions">
        <button type="submit" className="button button--small" disabled={busy}>
          Guardar
        </button>
        <button type="button" className="button button--ghost button--small" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
