import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Model output is untrusted: no raw HTML, executable URLs or remote image loads. */
export function MarkdownAnswer({ content }: { content: string }) {
  return <div className="markdown-answer"><Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
    a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
    img: ({ alt }) => alt ? <span className="muted">[Image: {alt}]</span> : null,
    table: ({ children }) => <div className="answer-table"><table>{children}</table></div>,
  }}>{content}</Markdown></div>;
}
