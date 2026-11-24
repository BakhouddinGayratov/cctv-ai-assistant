import { Fragment, type ReactNode } from "react";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;

function inline(text: string, keyBase: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const k = `${keyBase}-${i}`;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={k} className="font-semibold text-fg">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={k} className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[0.85em]">{part.slice(1, -1)}</code>;
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_")))
      return <em key={k}>{part.slice(1, -1)}</em>;
    return <Fragment key={k}>{part}</Fragment>;
  });
}

/** Minimal, xavfsiz markdown (React elementlari — HTML inyeksiyasi yo'q). */
export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = (i: number) => {
    if (list.length) {
      blocks.push(<ul key={`ul-${i}`} className="my-1.5 space-y-1 pl-1">{list}</ul>);
      list = [];
    }
  };
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    const bullet = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      list.push(
        <li key={i} className="flex gap-2">
          <span aria-hidden className="mt-[0.55em] size-1.5 shrink-0 rounded-full bg-brand/70" />
          <span>{inline(bullet[1] ?? "", `li${i}`)}</span>
        </li>,
      );
      return;
    }
    flush(i);
    if (!line.trim()) return;
    if (/^-{3,}$/.test(line.trim())) {
      blocks.push(<hr key={i} className="my-2 border-line" />);
      return;
    }
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(<p key={i} className="mt-2 font-semibold text-fg">{inline(heading[1] ?? "", `h${i}`)}</p>);
      return;
    }
    blocks.push(<p key={i}>{inline(line, `p${i}`)}</p>);
  });
  flush(lines.length);
  return <div className="space-y-1.5 text-[13.5px] leading-relaxed text-fg/90">{blocks}</div>;
}
