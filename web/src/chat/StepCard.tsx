import type { Step, ToolCallState } from '../state/reducer';
import { redactArguments } from './redact';
import { strings } from '../strings';

/**
 * A collapsible card inside the assistant message (REQ-009): a thinking summary, or a tool call with its name,
 * redacted arguments, a business-vs-generic badge, and the result (status, summary, trace). Text that came from
 * the legacy screen is shown in an "untrusted legacy data" style so a reader can tell the system's words from
 * the agent's.
 */

export interface StepCardProps {
  step: Step;
  /** Resolved when the step is a tool call. */
  call?: ToolCallState;
}

function Untrusted({ text }: { text: string }) {
  return (
    <span className="untrusted-data" title={strings.step.untrustedTitle}>
      <span className="untrusted-tag">{strings.step.untrustedTag}</span>
      <q className="untrusted-text">{text}</q>
    </span>
  );
}

function ResultView({ call }: { call: ToolCallState }) {
  if (call.status === 'running') return <p className="step-pending">{strings.step.running}</p>;
  const resultData = call.result && typeof call.result === 'object' ? (call.result as { data?: unknown }).data : null;
  return (
    <div className="step-result" data-status={call.status}>
      <p className="step-status">
        {strings.step.statusLabel}: <span>{call.status}</span>
        {call.errorCode && <span className="step-error"> ({call.errorCode})</span>}
      </p>
      {call.errorCode === 'ambiguous_ack' && (
        <p className="step-ambiguous" role="note">
          {strings.states.ambiguousAckShort}
        </p>
      )}
      {call.summary && <p className="step-summary">{call.summary}</p>}
      {resultData != null && (
        <div className="step-data">
          {/* Values here originate from legacy screens: label them as untrusted data. */}
          {Object.entries(resultData as Record<string, unknown>).map(([k, v]) => (
            <div key={k} className="step-data-row">
              <span className="step-data-key">{k}</span>
              <Untrusted text={String(v)} />
            </div>
          ))}
        </div>
      )}
      {call.truncated && <p className="step-truncated">{strings.step.truncated}</p>}
    </div>
  );
}

export function StepCard({ step, call }: StepCardProps) {
  if (step.kind === 'thinking') {
    return (
      <details className="step-card step-thinking">
        <summary>
          <span className="step-kind">{strings.step.thinking}</span>
        </summary>
        <p className="step-summary">{step.summary}</p>
      </details>
    );
  }
  if (!call) return null;
  const args = redactArguments(call.arguments);
  return (
    <details className="step-card step-tool" data-kind={call.toolKind} open={call.status === 'running'}>
      <summary>
        <span className="step-tool-name">{call.tool}</span>
        <span className={`step-badge step-badge-${call.toolKind}`}>
          {call.toolKind === 'business' ? strings.step.business : strings.step.generic}
        </span>
        {call.mayCommit && <span className="step-badge step-badge-commit">{strings.step.mayCommit}</span>}
      </summary>
      {args.length > 0 && (
        <dl className="step-args">
          {args.map((a) => (
            <div key={a.key} className="step-arg">
              <dt>{a.key}</dt>
              <dd className={a.value === '<redacted>' ? 'step-arg-redacted' : undefined}>{a.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <ResultView call={call} />
    </details>
  );
}
