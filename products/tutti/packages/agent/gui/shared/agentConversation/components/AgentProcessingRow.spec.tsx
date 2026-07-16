import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentProcessingRow } from "./AgentProcessingRow";

describe("AgentProcessingRow", () => {
  it("renders the processing label inside a stable text span", () => {
    render(
      <AgentProcessingRow
        row={{
          kind: "processing",
          id: "processing",
          turnId: null,
          label: "正在规划下一步",
          occurredAtUnixMs: null
        }}
        label="Planning next moves"
      />
    );

    const label = screen.getByText("正在规划下一步");
    expect(label.className).not.toContain("tsh-inline-scanlight-line");
    expect(label.parentElement?.className).toContain("font-semibold");
    expect(
      label.parentElement?.querySelector(
        ".tsh-inline-loading-ellipsis--entry-timing"
      )
    ).toBeTruthy();
  });

  it("does not render a leading loading icon before the processing label", () => {
    const { container } = render(
      <AgentProcessingRow
        row={{
          kind: "processing",
          id: "processing",
          turnId: null,
          label: "正在规划下一步",
          occurredAtUnixMs: null
        }}
        label="Planning next moves"
      />
    );

    expect(container.querySelector("video")).not.toBeInTheDocument();
    expect(
      container.querySelector(".tsh-inline-scanlight-icon")
    ).not.toBeInTheDocument();
  });
});
