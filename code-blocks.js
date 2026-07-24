const shellCommands = new Set([
  'apt',
  'curl',
  'dnf',
  'echo',
  'flatpak',
  'install',
  'rpm',
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

function highlightShell(source) {
  let cursor = 0;
  let result = '';

  for (const match of source.matchAll(tokenPattern)) {
    const token = match[0];
    let type;

    result += escapeHtml(source.slice(cursor, match.index));

    if (token.startsWith('"') || token.startsWith("'")) {
      type = 'string';
    } else if (token.startsWith('http') || token.startsWith('/') || token.startsWith('.')) {
      type = 'path';
    } else if (token.startsWith('-')) {
      type = 'option';
    } else if (/^\d+$/.test(token)) {
      type = 'number';
    } else if (token === '\\' || token.includes('|') || token.includes('>')) {
      type = 'operator';
    } else if (shellCommands.has(token)) {
      type = 'command';
    }

    result += type
      ? `<span class="token-${type}">${escapeHtml(token)}</span>`
      : escapeHtml(token);
    cursor = match.index + token.length;
  }

  return result + escapeHtml(source.slice(cursor));
}

function copyFallback(value) {
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();

  if (!copied) {
    throw new Error('Could not copy code');
  }
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
  } else {
    copyFallback(value);
  }
}

for (const code of document.querySelectorAll('code.language-shell')) {
  const source = code.textContent;
  code.innerHTML = highlightShell(source);

  const button = document.createElement('button');
  button.className = 'copy-button';
  button.type = 'button';
  button.setAttribute('aria-label', 'Copy code');
  button.title = 'Copy code';
  button.innerHTML = `
    <svg class="copy-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <rect width="14" height="14" x="8" y="8" rx="2"></rect>
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
    </svg>
    <svg class="check-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="m5 12 4 4L19 6"></path>
    </svg>
  `;

  let resetTimer;
  button.addEventListener('click', async () => {
    try {
      await copyText(source);
      button.dataset.copied = '';
      button.setAttribute('aria-label', 'Copied');
      button.title = 'Copied';
      clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        delete button.dataset.copied;
        button.setAttribute('aria-label', 'Copy code');
        button.title = 'Copy code';
      }, 2000);
    } catch {
      button.setAttribute('aria-label', 'Copy failed');
      button.title = 'Copy failed';
    }
  });

  code.parentElement.append(button);
}
