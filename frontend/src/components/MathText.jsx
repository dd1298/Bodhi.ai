import React from "react";
import { InlineMath, BlockMath } from "react-katex";
import "katex/dist/katex.min.css";

/**
 * Render a string that may contain LaTeX delimited by `$...$` (inline) or
 * `$$...$$` (block). Plain text segments are preserved as-is, math segments
 * are rendered via KaTeX.
 */
const splitMath = (text) => {
  if (!text) return [];
  const parts = [];
  let i = 0;
  while (i < text.length) {
    if (text.startsWith("$$", i)) {
      const end = text.indexOf("$$", i + 2);
      if (end === -1) {
        parts.push({ kind: "text", value: text.slice(i) });
        break;
      }
      parts.push({ kind: "block", value: text.slice(i + 2, end) });
      i = end + 2;
    } else if (text[i] === "$") {
      const end = text.indexOf("$", i + 1);
      if (end === -1) {
        parts.push({ kind: "text", value: text.slice(i) });
        break;
      }
      parts.push({ kind: "inline", value: text.slice(i + 1, end) });
      i = end + 1;
    } else {
      const next = text.indexOf("$", i);
      if (next === -1) {
        parts.push({ kind: "text", value: text.slice(i) });
        break;
      }
      parts.push({ kind: "text", value: text.slice(i, next) });
      i = next;
    }
  }
  return parts;
};

export default function MathText({ text, className = "" }) {
  const segments = splitMath(text || "");
  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (seg.kind === "inline") {
          try {
            return <InlineMath key={i} math={seg.value} />;
          } catch {
            return <code key={i}>{seg.value}</code>;
          }
        }
        if (seg.kind === "block") {
          try {
            return <BlockMath key={i} math={seg.value} />;
          } catch {
            return <pre key={i}>{seg.value}</pre>;
          }
        }
        return (
          <span key={i} style={{ whiteSpace: "pre-wrap" }}>
            {seg.value}
          </span>
        );
      })}
    </span>
  );
}
