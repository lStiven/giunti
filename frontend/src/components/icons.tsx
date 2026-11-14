/**
 * Icons from Lucide (https://lucide.dev, ISC license): decorative (aria-hidden) and sized by the
 * surrounding font through the `icon` class. Components import them from here, so the icon set
 * can change in one place.
 */
import {
  Check,
  CircleAlert,
  CircleCheckBig,
  Clock,
  Copy,
  Cpu,
  Download,
  FileText,
  FileUp,
  KeyRound,
  RotateCw,
  Upload,
  type LucideIcon,
} from "lucide-react";
import type { ReactElement } from "react";

const STROKE_WIDTH = 1.8;

function icon(Glyph: LucideIcon): () => ReactElement {
  return function DecorativeIcon(): ReactElement {
    return (
      <Glyph className="icon" strokeWidth={STROKE_WIDTH} aria-hidden="true" focusable="false" />
    );
  };
}

export const UploadIcon = icon(Upload);
export const FileIcon = icon(FileText);
export const CheckIcon = icon(Check);
export const KeyIcon = icon(KeyRound);
export const CopyIcon = icon(Copy);
export const DownloadIcon = icon(Download);
export const AlertIcon = icon(CircleAlert);
/** Success: the extraction finished or a key was issued. */
export const SparkIcon = icon(CircleCheckBig);
export const WaitIcon = icon(Clock);
export const RetryIcon = icon(RotateCw);
export const ModelIcon = icon(Cpu);
export const ChangeFileIcon = icon(FileUp);
