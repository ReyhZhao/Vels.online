export default function SlideOver({ open, onClose, title, loading, children }) {
  return (
    <>
      <div
        data-testid="slideover-backdrop"
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`fixed inset-y-0 right-0 w-full max-w-md bg-background shadow-2xl z-50 transform transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        role="dialog"
        aria-modal={open ? 'true' : undefined}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border">
            <h2 className="text-base font-semibold text-foreground">{title}</h2>
            <button
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {open && (
              loading ? (
                <p role="status" className="px-6 py-8 text-sm text-muted-foreground">Loading…</p>
              ) : (
                children
              )
            )}
          </div>
        </div>
      </div>
    </>
  );
}
