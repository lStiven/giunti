import type { ReactElement } from "react";

import type { ReasoningMode } from "../types/questionnaire";

interface ModePickerProps {
  selected: ReasoningMode;
  disabled: boolean;
  onSelect: (mode: ReasoningMode) => void;
}

export const MODE_LABELS: Record<ReasoningMode, string> = {
  fast: "Rápido",
  precise: "Preciso",
};

const MODE_DESCRIPTIONS: Record<ReasoningMode, string> = {
  fast: "El modelo razona lo justo: tarda menos y consume menos. Suficiente para la mayoría de los cuestionarios.",
  precise:
    "El modelo razona más antes de responder. Para documentos difíciles: escaneados, con figuras o con la clave en imagen. Puede tardar varios minutos.",
};

/** Reasoning mode of the chosen model, as a radio group (shown only for models with both). */
export function ModePicker({ selected, disabled, onSelect }: ModePickerProps): ReactElement {
  const modes: ReasoningMode[] = ["fast", "precise"];
  return (
    <fieldset className="modes" disabled={disabled}>
      <legend className="modes__legend">Modo de lectura</legend>
      {modes.map((mode) => (
        <label
          key={mode}
          className={`mode-option${mode === selected ? " mode-option--selected" : ""}`}
        >
          <input
            className="visually-hidden"
            type="radio"
            name="mode"
            value={mode}
            checked={mode === selected}
            onChange={() => {
              onSelect(mode);
            }}
          />
          <span className="mode-option__name">{MODE_LABELS[mode]}</span>
          <span className="mode-option__description">{MODE_DESCRIPTIONS[mode]}</span>
        </label>
      ))}
    </fieldset>
  );
}
