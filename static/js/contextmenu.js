// Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

const menu = document.getElementById('context-menu');

export function showContextMenu(e, actions) {
  e.preventDefault();
  menu.innerHTML = '';

  actions.forEach(action => {
    if (action.separator) {
      const sep = document.createElement('div');
      sep.className = 'context-menu__separator';
      menu.appendChild(sep);
      return;
    }

    if (action.submenu) {
      const el = document.createElement('div');
      el.className = 'context-menu__item context-menu__item--submenu';
      el.textContent = action.label;
      el.style.position = 'relative';

      const sub = document.createElement('div');
      sub.className = 'context-menu__submenu';
      action.submenu.forEach(child => {
        const childEl = document.createElement('div');
        childEl.className = 'context-menu__item';
        childEl.textContent = child.label;
        childEl.addEventListener('click', (ev) => {
          ev.stopPropagation();
          hide();
          child.onClick();
        });
        sub.appendChild(childEl);
      });
      el.appendChild(sub);
      menu.appendChild(el);
      return;
    }

    const el = document.createElement('div');
    el.className = `context-menu__item${action.destructive ? ' context-menu__item--destructive' : ''}`;
    el.textContent = action.label;
    el.addEventListener('click', () => {
      hide();
      action.onClick();
    });
    menu.appendChild(el);
  });

  const x = Math.min(e.clientX, window.innerWidth - 200);
  const y = Math.min(e.clientY, window.innerHeight - menu.children.length * 36);
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.classList.add('is-visible');
}

function hide() {
  menu.classList.remove('is-visible');
}

document.addEventListener('click', hide);
document.addEventListener('contextmenu', (e) => {
  if (!menu.contains(e.target)) hide();
});
