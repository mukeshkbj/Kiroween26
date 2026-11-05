import type { Message as Msg, TurnState } from '../state/reducer';
import { SafeText } from './SafeText';
import { StepCard } from './StepCard';
import { strings } from '../strings';
import type { ToolCallState } from '../state/reducer';

/**
 * One chat message (REQ-007). User and system messages are plain; an assistant message carries its turn's step
 * cards (thinking, tool calls) above the streamed answer. Assistant and legacy text are visually distinct
 * (REQ-009): the answer is prose, step results wrap legacy data in an untrusted style.
 */

export interface MessageProps {
  message: Msg;
  /** The turn this assistant message belongs to, for its step cards. */
  turn?: TurnState;
  toolCalls: Record<string, ToolCallState>;
}

export function Message({ message, turn, toolCalls }: MessageProps) {
  if (message.kind === 'user') {
    return (
      <li className="msg msg-user" data-status={message.status}>
        <span className="msg-who">{strings.chat.you}</span>
        <div className="msg-body">{message.text}</div>
        {message.status === 'failed' && <p className="msg-failed">{strings.chat.sendFailed}</p>}
      </li>
    );
  }
  if (message.kind === 'system') {
    return (
      <li className={`msg msg-system msg-${message.level}`} data-code={message.code ?? undefined}>
        <span className="msg-who">{strings.chat.system}</span>
        <div className="msg-body">{message.text}</div>
      </li>
    );
  }
  // assistant
  const steps = turn?.steps ?? [];
  return (
    <li className="msg msg-assistant">
      <span className="msg-who">{strings.chat.seance}</span>
      {steps.length > 0 && (
        <div className="msg-steps">
          {steps.map((s) => (
            <StepCard key={s.id} step={s} call={s.kind === 'tool' ? toolCalls[s.callId] : undefined} />
          ))}
        </div>
      )}
      <div className="msg-body">
        {message.text ? <SafeText text={message.text} /> : <span className="msg-streaming">{strings.chat.streaming}</span>}
      </div>
    </li>
  );
}
