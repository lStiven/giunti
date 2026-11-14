/** Checks done before uploading, so obvious mistakes do not wait for the server. */

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".xlsx"] as const;
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(",");

const DEFAULT_MAX_FILE_MB = 20;
const BYTES_PER_MB = 1024 * 1024;

export const MAX_FILE_MB: number =
  Number(import.meta.env.VITE_MAX_FILE_MB ?? DEFAULT_MAX_FILE_MB) || DEFAULT_MAX_FILE_MB;

export type FileProblem = "UNSUPPORTED_FORMAT" | "EMPTY_FILE" | "FILE_TOO_LARGE";

export function fileProblem(file: File, maxMegabytes: number = MAX_FILE_MB): FileProblem | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "UNSUPPORTED_FORMAT";
  }
  if (file.size === 0) {
    return "EMPTY_FILE";
  }
  if (file.size > maxMegabytes * BYTES_PER_MB) {
    return "FILE_TOO_LARGE";
  }
  return null;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  }
  return `${(bytes / BYTES_PER_MB).toFixed(1)} MB`;
}
