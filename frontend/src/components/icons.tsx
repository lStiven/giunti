/** Inline SVG icons: decorative (aria-hidden), sized by the surrounding font. */
import type { ReactElement, ReactNode } from "react";

function Icon({ children }: { children: ReactNode }): ReactElement {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function UploadIcon(): ReactElement {
  return (
    <Icon>
      <path d="M12 15V4m0 0-4 4m4-4 4 4" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Icon>
  );
}

export function FileIcon(): ReactElement {
  return (
    <Icon>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </Icon>
  );
}

export function CheckIcon(): ReactElement {
  return (
    <Icon>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </Icon>
  );
}

export function KeyIcon(): ReactElement {
  return (
    <Icon>
      <circle cx="8" cy="15" r="4" />
      <path d="m11 12 8-8m-3 3 2 2m-4 0 1.5 1.5" />
    </Icon>
  );
}

export function CopyIcon(): ReactElement {
  return (
    <Icon>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V6a2 2 0 0 1 2-2h9" />
    </Icon>
  );
}

export function DownloadIcon(): ReactElement {
  return (
    <Icon>
      <path d="M12 4v11m0 0-4-4m4 4 4-4" />
      <path d="M4 17v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
    </Icon>
  );
}

export function AlertIcon(): ReactElement {
  return (
    <Icon>
      <path d="M12 9v4m0 3.5v.01" />
      <path d="M10.3 4.2 2.8 17.4A2 2 0 0 0 4.5 20.4h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z" />
    </Icon>
  );
}

export function SparkIcon(): ReactElement {
  return (
    <Icon>
      <path d="M12 3v4m0 10v4M3 12h4m10 0h4M6 6l2.5 2.5m7 7L18 18M6 18l2.5-2.5m7-7L18 6" />
    </Icon>
  );
}
