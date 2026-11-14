import { useId, useState, type DragEvent, type ReactElement } from "react";

import { ACCEPT_ATTRIBUTE, MAX_FILE_MB, fileProblem, formatSize } from "../files";
import { errorText } from "../messages";
import { FileIcon, UploadIcon } from "./icons";

interface FileDropzoneProps {
  file: File | null;
  disabled: boolean;
  onFile: (file: File | null) => void;
}

/** Step 2: drag and drop or pick a file. Invalid files are explained here, before uploading. */
export function FileDropzone({ file, disabled, onFile }: FileDropzoneProps): ReactElement {
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const inputId = useId();
  const hintId = useId();

  const choose = (candidate: File | undefined): void => {
    if (candidate === undefined) {
      return;
    }
    const issue = fileProblem(candidate);
    if (issue === null) {
      setProblem(null);
      onFile(candidate);
    } else {
      const text = errorText(issue);
      setProblem(`${text.title}. ${text.hint}`);
      onFile(null);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragging(false);
    if (!disabled) {
      choose(event.dataTransfer.files[0]);
    }
  };

  const classes = [
    "dropzone",
    dragging ? "dropzone--dragging" : "",
    file ? "dropzone--filled" : "",
    disabled ? "dropzone--disabled" : "",
  ].join(" ");

  return (
    // eslint-disable-next-line jsx-a11y-x/no-static-element-interactions -- dragging is a mouse-only shortcut; keyboard and screen reader users use the file input
    <div
      className="dropzone-wrapper"
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setDragging(true);
        }
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <input
        id={inputId}
        className="visually-hidden"
        type="file"
        accept={ACCEPT_ATTRIBUTE}
        disabled={disabled}
        aria-describedby={hintId}
        onChange={(event) => {
          choose(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      <label htmlFor={inputId} className={classes}>
        {file ? (
          <>
            <span className="dropzone__icon dropzone__icon--file">
              <FileIcon />
            </span>
            <span className="dropzone__title">{file.name}</span>
            <span className="dropzone__hint">
              {formatSize(file.size)} · Haz clic o arrastra otro archivo para cambiarlo
            </span>
          </>
        ) : (
          <>
            <span className="dropzone__icon">
              <UploadIcon />
            </span>
            <span className="dropzone__title">Arrastra tu cuestionario aquí</span>
            <span className="dropzone__hint">o haz clic para elegirlo</span>
          </>
        )}
      </label>
      <p className="dropzone__formats" id={hintId}>
        PDF, Word (.docx) o Excel (.xlsx) · hasta {MAX_FILE_MB} MB
      </p>
      {problem && (
        <p className="field-error" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
