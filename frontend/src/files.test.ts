import { describe, expect, it } from "vitest";

import { fileProblem } from "./files";

const MB = 1024 * 1024;

function file(name: string, size: number): File {
  const sized = new File([], name);
  Object.defineProperty(sized, "size", { value: size });
  return sized;
}

describe("fileProblem", () => {
  it.each(["test.pdf", "Test.DOCX", "notas.final.xlsx"])("accepts %s", (name) => {
    expect(fileProblem(file(name, 100), 20)).toBeNull();
  });

  it.each(["test.doc", "test.xls", "test.docm", "test.txt", "pdf", "test.pdf.zip"])(
    "rejects %s as an unsupported format",
    (name) => {
      expect(fileProblem(file(name, 100), 20)).toBe("UNSUPPORTED_FORMAT");
    },
  );

  it("rejects empty files", () => {
    expect(fileProblem(file("test.pdf", 0), 20)).toBe("EMPTY_FILE");
  });

  it("accepts a file exactly at the size limit and rejects one byte more", () => {
    expect(fileProblem(file("test.pdf", 20 * MB), 20)).toBeNull();
    expect(fileProblem(file("test.pdf", 20 * MB + 1), 20)).toBe("FILE_TOO_LARGE");
  });
});
