// Which in-app previewer (if any) can render an attachment: 'image' | 'pdf' |
// 'text' | 'email' | null (download-only). Mirrors the backend
// `attachment_preview_kind`: an explicit content_type wins, the filename
// extension is only a fallback for generic types, and text/html is never
// previewed as a raw file (only a sandboxed email HTML body is rendered).
export function previewKind(attachment) {
  const ct = (attachment?.content_type || '').toLowerCase().split(';')[0].trim();
  const name = (attachment?.filename || '').toLowerCase();

  if (ct.startsWith('image/')) return 'image';
  if (ct === 'application/pdf') return 'pdf';
  if (ct === 'message/rfc822') return 'email';
  if (ct === 'text/html') return null;
  if (ct.startsWith('text/')) return 'text';

  if (ct === '' || ct === 'application/octet-stream' || ct === 'binary/octet-stream') {
    if (/\.(png|jpg|jpeg|gif|webp|bmp|svg)$/.test(name)) return 'image';
    if (name.endsWith('.pdf')) return 'pdf';
    if (name.endsWith('.eml')) return 'email';
    if (/\.(txt|log|csv|json|md)$/.test(name)) return 'text';
  }
  return null;
}

export function isPreviewable(attachment) {
  return previewKind(attachment) !== null;
}
