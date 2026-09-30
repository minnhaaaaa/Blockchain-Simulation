import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownAnswer } from "../src/components/MarkdownAnswer";

describe("agent answer rendering", () => {
  it("renders Markdown headings, emphasis, lists, tables and code", () => {
    const { container } = render(<MarkdownAnswer content={'## Summary\n\nA **capstone thesis** about integrity.\n\n1. First finding\n2. Second finding\n\n| Topic | Finding |\n| --- | --- |\n| Integrity | Verified |\n\n```python\nprint("hello")\n```'}/>);
    expect(screen.getByRole("heading", { name: "Summary", level: 2 })).toBeInTheDocument();
    expect(container.querySelector("strong")).toHaveTextContent("capstone thesis");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("table")).toHaveTextContent("Verified");
    expect(container.querySelector("pre code")).toHaveTextContent('print("hello")');
    expect(container.textContent).not.toContain("**");
  });
  it("does not execute HTML, unsafe links, or load remote images", () => {
    const { container } = render(<MarkdownAnswer content={'<script>alert(1)</script>\n\n[bad](javascript:alert%281%29)\n\n![tracking](https://untrusted.example/pixel)\n\n[Source](https://example.org/paper)'}/>);
    expect(container.querySelector("script, iframe, img")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("rel", "noopener noreferrer");
  });
  it("preserves literal characters inside code instead of globally stripping asterisks", () => {
    render(<MarkdownAnswer content={'Use `**kwargs` and multiply `2 * 3`.'}/>);
    expect(screen.getByText("**kwargs")).toBeInTheDocument();
    expect(screen.getByText("2 * 3")).toBeInTheDocument();
  });
});
