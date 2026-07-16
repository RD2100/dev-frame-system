import { describe, expect, it } from "vitest";
import {
  appendWorkspaceFileLinksToContent,
  extractWorkspaceFileLinksFromContent,
  extractPlainTextFromContent,
  normalizeWorkspaceFileLinkHref
} from "./richTextDocument";

describe("richTextDocument", () => {
  it("normalizes legacy plain text into searchable text output", () => {
    expect(extractPlainTextFromContent("hello legacy world")).toBe(
      "hello legacy world"
    );
  });

  it("appends workspaceFileLink nodes and extracts them back out", () => {
    const content = appendWorkspaceFileLinksToContent("", [
      { name: "demo.md", path: "workspace/tasks/task-1/attachments/demo.md" }
    ]);

    expect(content).toBe(
      "[demo.md](workspace/tasks/task-1/attachments/demo.md)"
    );
    expect(extractWorkspaceFileLinksFromContent(content)).toEqual([
      {
        name: "demo.md",
        path: "workspace/tasks/task-1/attachments/demo.md",
        href: "workspace/tasks/task-1/attachments/demo.md",
        kind: "file"
      }
    ]);
    expect(extractPlainTextFromContent(content)).toContain("demo.md");
  });

  it("preserves folder references with folder protocol and kind metadata", () => {
    const content = appendWorkspaceFileLinksToContent("", [
      {
        name: "specs",
        path: "workspace/tasks/task-1/attachments/specs",
        kind: "folder"
      }
    ]);

    expect(content).toBe("[specs](workspace/tasks/task-1/attachments/specs/)");
    expect(extractWorkspaceFileLinksFromContent(content)).toEqual([
      {
        name: "specs",
        path: "workspace/tasks/task-1/attachments/specs/",
        href: "workspace/tasks/task-1/attachments/specs/",
        kind: "folder"
      }
    ]);
    expect(
      normalizeWorkspaceFileLinkHref(
        "workspace/tasks/task-1/attachments/specs",
        "folder"
      )
    ).toBe("workspace/tasks/task-1/attachments/specs/");
  });

  it("extracts plain text from markdown content while keeping link labels", () => {
    expect(
      extractPlainTextFromContent(
        "目标：产出方案\n\n参考文件：[demo.md](/workspace/output/demo.md)\n- 第一项\n- 第二项"
      )
    ).toBe("目标：产出方案 参考文件： demo.md 第一项 第二项");
  });
});
