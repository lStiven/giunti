import { useEffect, useState, type ReactElement } from "react";

import { CopyIcon } from "./icons";

interface CopyButtonProps {
  text: string;
  label: string;
  className?: string;
}

type CopyState = "idle" | "copied" | "failed";

/** Copies `text` to the clipboard and confirms it (visibly and to screen readers). */
export function CopyButton({ text, label, className = "button" }: CopyButtonProps): ReactElement {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setState("idle");
    }, 2500);
    return (): void => {
      window.clearTimeout(timer);
    };
  }, [state]);

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  };

  return (
    <>
      <button type="button" className={className} onClick={() => void copy()}>
        <CopyIcon /> {state === "copied" ? "¡Copiado!" : label}
      </button>
      <span className="visually-hidden" aria-live="polite">
        {state === "copied" ? "Copiado al portapapeles" : ""}
        {state === "failed" ? "No se pudo copiar; selecciona el texto y cópialo a mano" : ""}
      </span>
    </>
  );
}
