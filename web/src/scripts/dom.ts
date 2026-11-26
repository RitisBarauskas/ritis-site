/** Looks up an element the page markup guarantees; a miss is a markup bug, so fail loudly. */
export function byId<T extends HTMLElement>(id: string, type: new () => T): T {
  const el = document.getElementById(id);
  if (!(el instanceof type)) {
    throw new Error(`#${id}: expected ${type.name}, got ${el ? el.constructor.name : 'nothing'}`);
  }
  return el;
}

export const all = <T extends Element = HTMLElement>(selector: string, root: ParentNode = document): T[] =>
  [...root.querySelectorAll<T>(selector)];
