const TOOLS = [
  { label: 'B',    title: 'Bold',   before: '**', after: '**' },
  { label: 'I',    title: 'Italic', before: '*',  after: '*'  },
  { label: '`',    title: 'Code',   before: '`',  after: '`'  },
  { label: '🔗',  title: 'Link',   link: true },
];

export default function MarkdownToolbar({ textareaRef, value, onChange }) {
  function applyTool(tool) {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end   = el.selectionEnd;
    const selected = value.slice(start, end);
    const replacement = tool.link
      ? `[${selected || 'link text'}](url)`
      : `${tool.before}${selected}${tool.after}`;
    onChange(value.slice(0, start) + replacement + value.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      const cursor = start + replacement.length;
      el.setSelectionRange(cursor, cursor);
    });
  }

  return (
    <div className="flex gap-1 pb-1">
      {TOOLS.map(tool => (
        <button
          key={tool.title}
          type="button"
          title={tool.title}
          aria-label={tool.title}
          onClick={() => applyTool(tool)}
          className="rounded px-2 py-0.5 text-xs font-mono text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        >
          {tool.label}
        </button>
      ))}
    </div>
  );
}
