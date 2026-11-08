import { useState, type KeyboardEvent } from 'react';
import { strings } from '../strings';
import type { ComposerBlock } from '../state/selectors';

/**
 * The input (REQ-008). Enter sends, Shift+Enter inserts a newline, Esc cancels the running turn. Disabled with a
 * stated reason while disconnected, observing, or while a confirmation is open. It can never send raw keys to the
 * mainframe; it only produces user_message / cancel_turn intents for the app to dispatch.
 */

export interface ComposerProps {
  block: ComposerBlock;
  /** A turn is running: Esc cancels it. */
  canCancel: boolean;
  onSend: (text: string) => void;
  onCancel: () => void;
  maxLength?: number;
}

export function Composer({ block, canCancel, onSend, onCancel, maxLength = 4000 }: ComposerProps) {
  const [text, setText] = useState('');
  const disabled = block !== null;
  const reason = block ? strings.chat.blocked[block] : null;

  const send = () => {
    const trimmed = text.trim();
    if (disabled || trimmed === '') return;
    onSend(trimmed.slice(0, maxLength));
    setText('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    } else if (e.key === 'Escape' && canCancel) {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <label className="sr-only" htmlFor="composer-input">
        {strings.chat.composerLabel}
      </label>
      <textarea
        id="composer-input"
        className="composer-input"
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, maxLength))}
        onKeyDown={onKeyDown}
        placeholder={strings.chat.placeholder}
        rows={2}
        maxLength={maxLength}
        disabled={disabled}
        aria-describedby={reason ? 'composer-reason' : undefined}
        aria-invalid={disabled || undefined}
      />
      <div className="composer-actions">
        {canCancel && (
          <button type="button" className="composer-cancel" onClick={onCancel}>
            {strings.chat.cancel}
          </button>
        )}
        <button type="submit" className="composer-send" disabled={disabled || text.trim() === ''}>
          {strings.chat.send}
        </button>
      </div>
      {reason && (
        <p id="composer-reason" className="composer-reason">
          {reason}
        </p>
      )}
    </form>
  );
}
