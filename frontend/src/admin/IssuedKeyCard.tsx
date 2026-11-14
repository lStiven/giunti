import { useEffect, useRef, type ReactElement } from "react";

import { CopyButton } from "../components/CopyButton";
import { SparkIcon } from "../components/icons";
import type { IssuedKey } from "./api";

interface IssuedKeyCardProps {
  issued: IssuedKey;
  onDone: () => void;
}

/** The new invitation, shown once: the server only keeps the key's hash. */
export function IssuedKeyCard({ issued, onDone }: IssuedKeyCardProps): ReactElement {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <section className="issued" aria-labelledby="issued-title">
      <span className="result__spark">
        <SparkIcon />
      </span>
      <div className="issued__body">
        <h2 className="issued__title" id="issued-title" ref={heading} tabIndex={-1}>
          Invitación lista para {issued.client.name}
        </h2>
        <p>
          Envíale este enlace por correo o mensaje: al abrirlo entra directamente, sin escribir
          ninguna clave.
        </p>
        <p className="issued__warning">
          Cópialo ahora: por seguridad no se vuelve a mostrar. Si se pierde, genera una nueva
          invitación.
        </p>
        <div className="issued__link">
          <code className="issued__url">{issued.invite_url}</code>
          <CopyButton text={issued.invite_url} label="Copiar enlace" />
        </div>
        <details className="issued__details">
          <summary>Ver la clave (para integraciones por API)</summary>
          <div className="issued__link">
            <code className="issued__url">{issued.api_key}</code>
            <CopyButton
              text={issued.api_key}
              label="Copiar clave"
              className="button button--ghost"
            />
          </div>
        </details>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Listo
        </button>
      </div>
    </section>
  );
}
