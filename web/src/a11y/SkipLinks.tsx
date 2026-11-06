import { strings } from '../strings';

/** Skip links (REQ-018): first in tab order, visible on focus, jump to the screen or the chat landmark. */
export function SkipLinks() {
  return (
    <nav className="skip-links" aria-label="Skip links">
      <a href="#screen-region">{strings.shell.skipToScreen}</a>
      <a href="#chat-region">{strings.shell.skipToChat}</a>
    </nav>
  );
}
