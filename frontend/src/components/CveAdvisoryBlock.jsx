const PLATFORM_LABELS = {
  ubuntu: 'Ubuntu',
  windows: 'Windows',
  macos: 'macOS',
};

export default function CveAdvisoryBlock({ advisories }) {
  if (!advisories?.length) return null;

  return (
    <div className="pt-3 border-t border-border">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">Remediation</p>
      <div className="space-y-4">
        {advisories.map(adv => (
          <div key={adv.platform}>
            <p className="text-sm font-medium text-foreground mb-1">
              {PLATFORM_LABELS[adv.platform] ?? adv.platform}
            </p>
            {adv.advisory_url || adv.remediation_text ? (
              <div className="space-y-1">
                {adv.advisory_url && (
                  <a
                    href={adv.advisory_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    View vendor advisory →
                  </a>
                )}
                {adv.remediation_text && (
                  <p className="text-sm text-foreground leading-relaxed">{adv.remediation_text}</p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground italic">No advisory available.</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
