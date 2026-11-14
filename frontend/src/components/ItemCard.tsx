import type { CSSProperties, ReactElement } from "react";

import { ITEM_TYPE_LABELS } from "../messages";
import type { Alternative, Item } from "../types/questionnaire";
import { CheckIcon } from "./icons";

interface ItemCardProps {
  item: Item;
  /** Position in the list, used to stagger the entrance animation. */
  index: number;
}

export function ItemCard({ item, index }: ItemCardProps): ReactElement {
  const answers = new Set(item.respuesta_correcta ?? []);
  const style = { "--i": Math.min(index, 12) } as CSSProperties;

  return (
    <li className="item-card" style={style}>
      <div className="item-card__header">
        <span className="item-card__number">{item.numero}</span>
        <span className="tag">{ITEM_TYPE_LABELS[item.tipo]}</span>
      </div>
      <p className="item-card__statement">{item.enunciado}</p>
      {item.tipo === "emparejamiento" ? (
        <MatchingColumns item={item} />
      ) : (
        item.alternativas.length > 0 && (
          <ul className="options">
            {item.alternativas.map((alternative) => (
              <OptionRow
                key={String(alternative.valor)}
                alternative={alternative}
                correct={answers.has(String(alternative.valor))}
              />
            ))}
          </ul>
        )
      )}
    </li>
  );
}

function OptionRow({
  alternative,
  correct,
}: {
  alternative: Alternative;
  correct: boolean;
}): ReactElement {
  return (
    <li className={`option${correct ? " option--correct" : ""}`}>
      <span className="option__value">{alternative.valor}</span>
      <span className="option__text">{alternative.texto ?? <em>Figura</em>}</span>
      {correct && (
        <span className="option__mark">
          <CheckIcon />
          <span className="visually-hidden">Respuesta correcta</span>
        </span>
      )}
    </li>
  );
}

function MatchingColumns({ item }: { item: Item }): ReactElement {
  return (
    <>
      <div className="matching">
        <ul className="options">
          {item.premisas.map((premise) => (
            <OptionRow key={String(premise.valor)} alternative={premise} correct={false} />
          ))}
        </ul>
        <ul className="options">
          {item.alternativas.map((alternative) => (
            <OptionRow key={String(alternative.valor)} alternative={alternative} correct={false} />
          ))}
        </ul>
      </div>
      {item.respuesta_correcta && (
        <p className="matching__answer">
          <CheckIcon /> Respuesta: {item.respuesta_correcta.join(", ")}
        </p>
      )}
    </>
  );
}
