import { useEffect, useRef } from 'react';
import { Message } from './Message';
import { Composer } from './Composer';
import { strings } from '../strings';
import type { AppState } from '../state/reducer';
import { composerBlock, activeTurnId } from '../state/selectors';

/**
 * The séance chat (REQ-007). A log region (role="log", polite) of user/assistant/system messages, with the
 * composer below. Assistant messages pull their turn's step cards. The UI only emits user_message / cancel_turn;
 * it never sends keys.
 */

export interface ChatProps {
  state: AppState;
  onSend: (text: string) => void;
  onCancel: (turnId: string) => void;
}

export function Chat({ state, onSend, onCancel }: ChatProps) {
  const logRef = useRef<HTMLDivElement | null>(null);
  const block = composerBlock(state);
  const turnId = activeTurnId(state);

  // Keep the newest message in view (plain behaviour; respects reduced motion by using auto, not smooth).
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages.length, state.messages[state.messages.length - 1]]);

  return (
    <section className="chat" aria-label={strings.chat.region}>
      {/* role="log" lives on a div: an <ol> may not carry that role, and it would also hide the list items. */}
      <div className="chat-log" ref={logRef} role="log" aria-live="polite" aria-label={strings.chat.log}>
        <ol className="chat-list">
          {state.messages.map((m) => (
            <Message
              key={m.id}
              message={m}
              turn={m.kind === 'assistant' && m.turnId ? state.turns[m.turnId] : undefined}
              toolCalls={state.toolCalls}
            />
          ))}
        </ol>
      </div>
      <Composer
        block={block}
        canCancel={turnId !== null && !state.observerOnly}
        onSend={onSend}
        onCancel={() => turnId && onCancel(turnId)}
      />
    </section>
  );
}
