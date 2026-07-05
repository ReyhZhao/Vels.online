import { useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';

// Constrained TipTap schema (PRD #632): the editor can ONLY produce the server's
// rich-text allowlist (p, br, strong, em, u, ul, ol, li + nested-list indent), so the
// client emits already-clean HTML and the server nh3 pass is defense-in-depth. Anything
// the StarterKit would add beyond the subset (headings, blockquote, code, rules, links,
// images) is disabled here.
const EXTENSIONS = [
  StarterKit.configure({
    heading: false,
    blockquote: false,
    codeBlock: false,
    code: false,
    horizontalRule: false,
    strike: false,
  }),
  Underline,
];

/** Strip all HTML tags, looping until stable so a removal can't re-expose a "<...>"
 *  sequence (guards CodeQL's incomplete-multi-character-sanitization; this is
 *  blank-detection only — real sanitization is the server-side nh3 pass). */
function stripTags(html) {
  let text = html;
  let prev;
  do {
    prev = text;
    text = text.replace(/<[^>]*>/g, '');
  } while (text !== prev);
  return text;
}

/** True when the editor HTML carries no visible text (TipTap renders empty as "<p></p>"). */
export function isBlankRichText(html) {
  if (!html) return true;
  return stripTags(html).replace(/&nbsp;/g, '').trim() === '';
}

function Btn({ onClick, active, label, children }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active || false}
      onMouseDown={(e) => {
        e.preventDefault(); // keep selection in the editor
        onClick();
      }}
      className={`min-w-[26px] rounded px-1.5 py-0.5 text-xs hover:bg-muted ${
        active ? 'bg-muted font-semibold text-foreground' : 'text-muted-foreground'
      }`}
    >
      {children}
    </button>
  );
}

export default function RichTextEditor({ value, onChange, onFocus, placeholder, minHeight = 80 }) {
  const editor = useEditor({
    extensions: EXTENSIONS,
    content: value || '',
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
    onFocus: () => onFocus?.(),
    editorProps: {
      attributes: {
        class: 'rte-content focus:outline-none',
        'data-placeholder': placeholder || '',
      },
    },
  });

  // Sync an external value (template switch / revert / generated summary) into the
  // editor — but never while it's focused, so per-keystroke typing can't fight the cursor.
  useEffect(() => {
    if (!editor) return;
    const next = value || '';
    if (!editor.isFocused && editor.getHTML() !== next) {
      editor.commands.setContent(next, false);
    }
  }, [value, editor]);

  if (!editor) return null;

  return (
    <div className="rounded border border-border bg-background" style={{ minHeight }}>
      <div className="flex flex-wrap items-center gap-0.5 border-b border-border px-1 py-0.5">
        <Btn label="Bold" active={editor.isActive('bold')}
          onClick={() => editor.chain().focus().toggleBold().run()}><b>B</b></Btn>
        <Btn label="Italic" active={editor.isActive('italic')}
          onClick={() => editor.chain().focus().toggleItalic().run()}><i>I</i></Btn>
        <Btn label="Underline" active={editor.isActive('underline')}
          onClick={() => editor.chain().focus().toggleUnderline().run()}><u>U</u></Btn>
        <span className="mx-1 h-4 w-px bg-border" />
        <Btn label="Bullet list" active={editor.isActive('bulletList')}
          onClick={() => editor.chain().focus().toggleBulletList().run()}>•</Btn>
        <Btn label="Numbered list" active={editor.isActive('orderedList')}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}>1.</Btn>
        <Btn label="Increase indent"
          onClick={() => editor.chain().focus().sinkListItem('listItem').run()}>⇥</Btn>
        <Btn label="Decrease indent"
          onClick={() => editor.chain().focus().liftListItem('listItem').run()}>⇤</Btn>
      </div>
      <EditorContent editor={editor} className="rte px-2 py-1.5 text-sm" />
    </div>
  );
}
