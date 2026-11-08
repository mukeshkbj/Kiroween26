import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { FILTERS, exportAudit, filterEntries, shortScreen, shortTime, windowSlice, type OutcomeFilter } from './filter';
import { strings } from '../strings';
import type { AuditEntry } from '../protocol/types';
import type { ChainStatus } from '../state/reducer';

/**
 * Audit drawer (REQ-015): a non-modal complementary region listing audit entries (REST load plus live
 * `audit_entry` events). Filter by outcome, export JSON, and show the chain status honestly: after live appends
 * the UI cannot verify hashes itself, so it says "unknown" until a refresh. Esc closes and returns focus to the
 * toggle. Values are shown exactly as given; the server already redacted them.
 */

export interface AuditDrawerProps {
  open: boolean;
  entries: AuditEntry[];
  chain: { status: ChainStatus; brokenSeq: number | null };
  onClose: () => void;
  onRefresh?: () => void;
  /** The button that opened the drawer; focus returns here on close. */
  toggleRef?: RefObject<HTMLElement | null>;
  rowHeight?: number;
  viewportHeight?: number;
  /** Test seam for the download. */
  onExport?: (json: string) => void;
}

function download(json: string) {
  if (typeof URL === 'undefined' || !URL.createObjectURL) return;
  const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'audit-log.json';
  a.click();
  URL.revokeObjectURL(url);
}

export function AuditDrawer(p: AuditDrawerProps) {
  const [filter, setFilter] = useState<OutcomeFilter>('all');
  const [scrollTop, setScrollTop] = useState(0);
  const rootRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const rowH = p.rowHeight ?? 28;
  const viewH = p.viewportHeight ?? 420;

  const shown = useMemo(() => filterEntries(p.entries, filter), [p.entries, filter]);
  const win = windowSlice(shown.length, scrollTop, viewH, rowH);
  const rows = shown.slice(win.start, win.end);

  // Move focus into the drawer on open; return it to the toggle on close.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (p.open && !wasOpen.current) closeRef.current?.focus();
    if (!p.open && wasOpen.current) p.toggleRef?.current?.focus();
    wasOpen.current = p.open;
  }, [p.open, p.toggleRef]);

  if (!p.open) return null;

  const chainText =
    p.chain.status === 'ok'
      ? strings.audit.chain.ok
      : p.chain.status === 'broken'
        ? strings.audit.chain.broken(p.chain.brokenSeq)
        : strings.audit.chain.unknown;

  return (
    <aside
      ref={rootRef}
      className="audit-drawer"
      aria-label={strings.audit.region}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          p.onClose();
        }
      }}
    >
      <header className="audit-head">
        <h2>{strings.audit.region}</h2>
        <button ref={closeRef} type="button" onClick={p.onClose} aria-label={strings.audit.close}>
          ×
        </button>
      </header>

      <p className={`audit-chain audit-chain-${p.chain.status}`}>
        {strings.audit.chain.label}: <span data-testid="chain-status">{chainText}</span>
        {p.onRefresh && (
          <button type="button" className="audit-refresh" onClick={p.onRefresh}>
            {strings.audit.refresh}
          </button>
        )}
      </p>

      <div className="audit-tools">
        <label>
          {strings.audit.filterLabel}{' '}
          <select value={filter} onChange={(e) => setFilter(e.target.value as OutcomeFilter)}>
            {FILTERS.map((f) => (
              <option key={f} value={f}>
                {strings.audit.filters[f]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => (p.onExport ? p.onExport(exportAudit(p.entries)) : download(exportAudit(p.entries)))}
          disabled={p.entries.length === 0}
        >
          {strings.audit.export}
        </button>
        <span className="audit-count" role="status">
          {strings.audit.count(shown.length, p.entries.length)}
        </span>
      </div>

      {p.entries.length === 0 ? (
        <p className="audit-empty">{strings.audit.empty}</p>
      ) : shown.length === 0 ? (
        <p className="audit-empty">{strings.audit.emptyFiltered}</p>
      ) : (
        <div
          className="audit-scroll"
          style={{ maxHeight: viewH, overflow: 'auto' }}
          onScroll={(e) => setScrollTop((e.target as HTMLElement).scrollTop)}
          tabIndex={0}
          aria-label={strings.audit.region}
        >
          <table className="audit-table">
            <thead>
              <tr>
                {(['time', 'seq', 'tool', 'screen', 'field', 'value', 'key', 'outcome', 'by'] as const).map((c) => (
                  <th key={c} scope="col">
                    {strings.audit.cols[c]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {win.padTop > 0 && (
                <tr aria-hidden="true" style={{ height: win.padTop }}>
                  <td colSpan={9} />
                </tr>
              )}
              {rows.map((e) => (
                <tr key={e.seq} data-outcome={e.outcome} style={{ height: rowH }}>
                  <td>{shortTime(e.ts)}</td>
                  <td>{e.seq}</td>
                  <td>{e.tool}</td>
                  <td title={e.screen_id ?? undefined}>{shortScreen(e.screen_id)}</td>
                  <td>{e.field ?? ''}</td>
                  <td>{e.value ?? ''}</td>
                  <td>{e.key ?? ''}</td>
                  <td className={`audit-outcome audit-outcome-${e.outcome}`}>{e.outcome}</td>
                  <td>{e.confirmed_by ?? ''}</td>
                </tr>
              ))}
              {win.padBottom > 0 && (
                <tr aria-hidden="true" style={{ height: win.padBottom }}>
                  <td colSpan={9} />
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </aside>
  );
}
