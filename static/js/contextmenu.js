const menu = document.getElementById('context-menu');

let currentActions = [];

export function showContextMenu(e, actions) {
  e.preventDefault();
  currentActions = actions;
  menu.innerHTML = '';

  actions.forEach(action => {
    if (action.separator) {
      const sep = document.createElement('div');
      sep.className = 'context-menu__separator';
      menu.appendChild(sep);
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
  const y = Math.min(e.clientY, window.innerHeight - actions.length * 36);
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
