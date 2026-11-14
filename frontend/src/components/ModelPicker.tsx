import type { ReactElement } from "react";

import type { ModelCatalog } from "../types/questionnaire";

interface ModelPickerProps {
  catalog: ModelCatalog;
  selected: string | null;
  disabled: boolean;
  onSelect: (modelId: string) => void;
}

/** Step 3: one card per model, as a radio group; the default model comes preselected. */
export function ModelPicker({
  catalog,
  selected,
  disabled,
  onSelect,
}: ModelPickerProps): ReactElement {
  const models = catalog.providers.flatMap((provider) =>
    provider.models.map((model) => ({ ...model, provider: provider.label })),
  );

  return (
    <fieldset className="models" disabled={disabled}>
      <legend className="visually-hidden">Modelo</legend>
      {models.map((model) => (
        <label
          key={model.id}
          className={`model-card${model.id === selected ? " model-card--selected" : ""}`}
        >
          <input
            className="visually-hidden"
            type="radio"
            name="model"
            value={model.id}
            checked={model.id === selected}
            onChange={() => {
              onSelect(model.id);
            }}
          />
          <span className="model-card__header">
            <span className="model-card__name">{model.label}</span>
            <span className="model-card__provider">{model.provider}</span>
          </span>
          <span className="model-card__description">{model.description}</span>
          <span className="model-card__tags">
            {model.is_default && <span className="tag tag--accent">Recomendado</span>}
            {model.free && <span className="tag">Gratuito</span>}
            {!model.vision && <span className="tag tag--warning">No lee escaneos</span>}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
