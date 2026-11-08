const shellCommands = new Set([
  'apt',
  'curl',
  'dnf',
  'echo',
  'flatpak',
  'gpg',
  'grep',
  'install',
  'pacman',
  'pacman-conf',
  'pacman-key',
  'rpm',
  'sed',
  'snap',
  'sudo',
  'tee',
  'wget',
  'zypper',
]);

const tokenPattern =
  /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|https?:\/\/[^\s"'<>]+|\\(?=\n)|--?[a-zA-Z0-9][\w-]*|(?:\/|\.\.?\/)[\w./*-]+|\b\d+\b|[|>]+|\b[\w-]+\b/g;

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function tokenType(token) {
  if (token.startsWith('"') || token.startsWith("'")) return 'string';
  if (token.startsWith('http') || token.startsWith('/') || token.startsWith('.')) return 'path';
  if (token.startsWith('-')) return 'option';
  if (/^\d+$/.test(token)) return 'number';
  if (token === '\\' || token.includes('|') || token.includes('>')) return 'operator';
  if (shellCommands.has(token)) return 'command';
  return undefined;
}

function highlightShell(source) {
  let cursor = 0;
  let result = '';

  for (const match of source.matchAll(tokenPattern)) {
    const token = match[0];
    const type = tokenType(token);
    result += escapeHtml(source.slice(cursor, match.index));
    result += type
      ? `<span class="token-${type}">${escapeHtml(token)}</span>`
      : escapeHtml(token);
    cursor = match.index + token.length;
  }

  return result + escapeHtml(source.slice(cursor));
}

const copyLabel = 'Copy code';

for (const code of document.querySelectorAll('code.language-shell')) {
  const source = code.textContent;
  code.innerHTML = highlightShell(source);

  const button = document.createElement('button');
  button.className = 'copy-button';
  button.type = 'button';
  button.innerHTML = `
    <svg class="copy-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect width="14" height="14" x="8" y="8" rx="2"></rect>
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
    </svg>
    <svg class="check-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="m5 12 4 4L19 6"></path>
    </svg>
  `;

  const setLabel = (label) => {
    button.setAttribute('aria-label', label);
    button.title = label;
  };
  setLabel(copyLabel);

  let resetTimer;

  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(source);
      button.dataset.copied = '';
      setLabel('Copied');
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        delete button.dataset.copied;
        setLabel(copyLabel);
      }, 2000);
    } catch {
      setLabel('Copy failed');
    }
  });

  // The card stays put while the code block scrolls horizontally.
  code.closest('.card').append(button);
}
