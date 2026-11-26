import { byId } from './dom';

const VISIBLE_MS = 3200;
let hideTimer: number | undefined;

export function toast(text: string): void {
  const el = byId('toast', HTMLDivElement);
  el.textContent = text;
  el.classList.add('show');
  window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(() => el.classList.remove('show'), VISIBLE_MS);
}
