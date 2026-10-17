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

function enhanceHorizontalScroll(pre, container) {
  const track = document.createElement('div');
  track.className = 'code-scrollbar';
  track.hidden = true;

  const thumb = document.createElement('div');
  thumb.className = 'code-scrollbar__thumb';
  thumb.tabIndex = 0;
  thumb.setAttribute('role', 'scrollbar');
  thumb.setAttribute('aria-label', 'Code block horizontal scroll');
  thumb.setAttribute('aria-orientation', 'horizontal');
  thumb.setAttribute('aria-valuemin', '0');
  thumb.setAttribute('aria-valuemax', '100');
  track.append(thumb);
  container.append(track);

  function refresh() {
    const maxScroll = pre.scrollWidth - pre.clientWidth;
    if (maxScroll <= 0) {
      track.hidden = true;
      return;
    }

    track.hidden = false;
    const thumbWidth = Math.max(36, Math.round(track.clientWidth * (pre.clientWidth / pre.scrollWidth)));
    const maxThumbOffset = track.clientWidth - thumbWidth;
    const thumbOffset = maxThumbOffset <= 0 ? 0 : (pre.scrollLeft / maxScroll) * maxThumbOffset;
    thumb.style.width = `${thumbWidth}px`;
    thumb.style.transform = `translateX(${thumbOffset}px)`;
    thumb.setAttribute('aria-valuenow', String(Math.round((pre.scrollLeft / maxScroll) * 100)));
  }

  pre.addEventListener('scroll', refresh, { passive: true });
  window.addEventListener('resize', refresh, { passive: true });
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(refresh);
    observer.observe(pre);
    observer.observe(track);
  }

  let startX = 0;
  let startScroll = 0;

  thumb.addEventListener('pointerdown', (event) => {
    startX = event.clientX;
    startScroll = pre.scrollLeft;
    thumb.setPointerCapture(event.pointerId);
    track.classList.add('is-dragging');
    event.preventDefault();
  });

  thumb.addEventListener('pointermove', (event) => {
    if (!thumb.hasPointerCapture(event.pointerId)) return;
    const maxScroll = pre.scrollWidth - pre.clientWidth;
    const maxThumbOffset = Math.max(1, track.clientWidth - thumb.offsetWidth);
    pre.scrollLeft = startScroll + ((event.clientX - startX) / maxThumbOffset) * maxScroll;
  });

  function endDrag(event) {
    if (thumb.hasPointerCapture(event.pointerId)) thumb.releasePointerCapture(event.pointerId);
    track.classList.remove('is-dragging');
  }

  thumb.addEventListener('pointerup', endDrag);
  thumb.addEventListener('pointercancel', endDrag);

  track.addEventListener('pointerdown', (event) => {
    if (event.target !== track) return;
    const maxScroll = pre.scrollWidth - pre.clientWidth;
    const maxThumbOffset = Math.max(1, track.clientWidth - thumb.offsetWidth);
    const targetOffset = event.clientX - track.getBoundingClientRect().left - thumb.offsetWidth / 2;
    pre.scrollLeft = (Math.min(maxThumbOffset, Math.max(0, targetOffset)) / maxThumbOffset) * maxScroll;
  });

  thumb.addEventListener('keydown', (event) => {
    const step = Math.max(48, Math.round(pre.clientWidth * 0.25));
    if (event.key === 'ArrowLeft') pre.scrollLeft -= step;
    else if (event.key === 'ArrowRight') pre.scrollLeft += step;
    else if (event.key === 'Home') pre.scrollLeft = 0;
    else if (event.key === 'End') pre.scrollLeft = pre.scrollWidth;
    else return;
    event.preventDefault();
  });

  requestAnimationFrame(refresh);
}

for (const code of document.querySelectorAll('code.language-shell')) {
  const source = code.textContent;
  code.innerHTML = highlightShell(source);

  const pre = code.parentElement;
  const container = document.createElement('div');
  container.className = 'code-block';
  pre.before(container);
  container.append(pre);
  enhanceHorizontalScroll(pre, container);

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

  container.append(button);
}
