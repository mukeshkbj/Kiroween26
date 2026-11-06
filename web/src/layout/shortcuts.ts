/**
 * Documented keyboard shortcuts (REQ-018). Every one needs a modifier (Alt+Shift), because single-key shortcuts
 * outside a widget collide with assistive technology and typing. They are listed in the help text and README.
 */

export type ShortcutId = 'audit' | 'map' | 'chat' | 'screen' | 'effects' | 'motion' | 'text';

export interface Shortcut {
  id: ShortcutId;
  /** KeyboardEvent.code, so it works across layouts. */
  code: string;
  label: string;
  description: string;
}

export const SHORTCUTS: readonly Shortcut[] = [
  { id: 'audit', code: 'KeyA', label: 'Alt+Shift+A', description: 'Toggle the audit log' },
  { id: 'map', code: 'KeyM', label: 'Alt+Shift+M', description: 'Switch between screen and spirit-map' },
  { id: 'chat', code: 'KeyC', label: 'Alt+Shift+C', description: 'Move focus to the chat' },
  { id: 'screen', code: 'KeyS', label: 'Alt+Shift+S', description: 'Move focus to the screen' },
  { id: 'effects', code: 'KeyE', label: 'Alt+Shift+E', description: 'Cycle effects: Full, Low, Off' },
  { id: 'motion', code: 'KeyR', label: 'Alt+Shift+R', description: 'Toggle reduced motion' },
  { id: 'text', code: 'KeyT', label: 'Alt+Shift+T', description: 'Toggle screen as text' },
];

type KeyLike = Pick<KeyboardEvent, 'code' | 'altKey' | 'shiftKey' | 'ctrlKey' | 'metaKey'>;

export function matchShortcut(e: KeyLike): ShortcutId | null {
  if (!e.altKey || !e.shiftKey || e.ctrlKey || e.metaKey) return null;
  return SHORTCUTS.find((s) => s.code === e.code)?.id ?? null;
}

export const nextEffects = (e: 'full' | 'low' | 'off'): 'full' | 'low' | 'off' =>
  e === 'full' ? 'low' : e === 'low' ? 'off' : 'full';
