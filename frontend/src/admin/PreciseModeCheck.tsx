import { useId, type ReactElement } from "react";

interface PreciseModeCheckProps {
  checked: boolean;
  className?: string;
  onChange: (checked: boolean) => void;
}

/** Whether the client may use the precise reasoning mode; unchecked means fast mode only. */
export function PreciseModeCheck({
  checked,
  className = "",
  onChange,
}: PreciseModeCheckProps): ReactElement {
  const id = useId();
  return (
    <div className={`check ${className}`.trim()}>
      <input
        id={id}
        type="checkbox"
        aria-describedby={`${id}-hint`}
        checked={checked}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
      <div>
        <label className="check__label" htmlFor={id}>
          Permitir modo preciso
        </label>
        <p className="check__hint" id={`${id}-hint`}>
          Razona más y sirve para documentos difíciles, pero tarda y cuesta varias veces más. Sin
          marcar, la clave solo usa el modo rápido.
        </p>
      </div>
    </div>
  );
}
