import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import "github-markdown-css/github-markdown-dark.css";

interface MarkdownContentProps {
  content: string;
  resolveImageSrc: (src?: string) => string | undefined;
}

export function MarkdownContent({ content, resolveImageSrc }: MarkdownContentProps) {
  return (
    <div className="markdown-body" style={{ background: "transparent" }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          img: ({ src, alt }) => <img src={resolveImageSrc(src)} alt={alt || ""} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
