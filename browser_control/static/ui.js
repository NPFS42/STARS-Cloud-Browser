'use strict';
const $ = id => document.getElementById(id);
const showStatus = message => { $('status').textContent = message; };
let inflight = false;
let viewport = { width: 1280, height: 800 };
let previewObjectUrl = '';
let pollTimer;
let wantLive = true;
let liveConnected = false;

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options });
  if (res.status === 401) { location.assign('/login'); throw new Error('Authentication required'); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `HTTP ${res.status}`);
  }
  return res;
}
async function command(op, args = {}) {
  return (await api('/api/command', {
    method: 'POST', headers: { 'Content-Type':'application/json', 'X-STARS-BROWSER-UI':'1' },
    body: JSON.stringify({ op, ...args })
  })).json();
}
async function execute(op, args = {}) {
  try { await command(op, args); await refresh(); }
  catch (err) { showStatus(`Error: ${err.message}`); }
}
async function refresh() {
  if (inflight || document.hidden) return;
  inflight = true;
  try {
    const data = await (await api('/api/status')).json();
    document.documentElement.dataset.connection = 'online';
    $('connectionBadge').textContent = 'Connected';
    viewport = data.viewport || viewport;
    if (document.activeElement !== $('url')) $('url').value = data.url === 'about:blank' ? '' : data.url;
    const tabs = $('tabs');
    const labels = data.tabs.map(t => (t.title || 'New tab').slice(0, 30));
    if (tabs.options.length !== labels.length || labels.some((v, i) => tabs.options[i]?.text !== v)) {
      tabs.replaceChildren();
      for (const [i, label] of labels.entries()) {
        const opt = document.createElement('option'); opt.value = String(i); opt.textContent = label; tabs.add(opt);
      }
    }
    tabs.value = String(data.tab);
    $('viewport').textContent = data.view_mode === 'compact' ? 'Compact' : 'Desktop';
    const remaining = Math.max(0, Number(data.mcp_grant_remaining) || 0);
    document.documentElement.dataset.aiGrant = remaining > 0 ? 'active' : 'locked';
    $('grantStatus').textContent = remaining > 0 ? ('Enabled · ' + Math.ceil(remaining / 60) + ' min remaining') : 'Locked · permission required';
    $('aiPill').textContent = remaining > 0 ? 'AI enabled' : 'AI locked';
    showStatus(`${data.title || 'New tab'} · ${data.url}`);
    if (!liveConnected) {
      // Fallback JPEG snapshot; while live, keep one long-lived stream.
      const img = await api('/api/screenshot?format=jpeg');
      const imageUrl = URL.createObjectURL(await img.blob());
      const previous = previewObjectUrl;
      previewObjectUrl = imageUrl;
      $('screen').src = imageUrl;
      if (previous) URL.revokeObjectURL(previous);
    }
  } catch(err) {
    document.documentElement.dataset.connection = 'offline';
    $('connectionBadge').textContent = 'Disconnected';
    showStatus('Error: ' + err.message);
  }
  finally { inflight = false; }
}
const bind = (id, op, args = () => ({})) => $(id).addEventListener('click', () => execute(op, args()));
bind('back','back'); bind('forward','forward'); bind('refresh','reload');
bind('go','navigate', () => ({ url:$('url').value }));
bind('new','tab_new'); bind('close','tab_close');
bind('send','type', () => ({ text:$('typing').value }));
bind('enter','press', () => ({ key:'Enter' }));
bind('tab','press', () => ({ key:'Tab' }));
bind('bksp','press', () => ({ key:'Backspace' }));
bind('esc','press', () => ({ key:'Escape' }));
bind('up','scroll', () => ({ dy:-650 }));
bind('down','scroll', () => ({ dy:650 }));
$('viewport').addEventListener('click', () => execute('viewport',{mode:$('viewport').textContent === 'Desktop' ? 'compact':'desktop'}));
$('tabs').addEventListener('change', () => execute('tab_select',{index:Number($('tabs').value)}));
$('url').addEventListener('keydown', e => { if(e.key === 'Enter') $('go').click(); });
$('typing').addEventListener('keydown', e => { if(e.key === 'Enter') $('send').click(); });
$('snapshot').addEventListener('click', refresh);
function syncLive() {
  if (wantLive && !document.hidden) {
    if (!liveConnected) {
      liveConnected = true;
      $('screen').src = `/api/live?fps=${Number($('liveFps').value)}`;
    }
  } else if (liveConnected) {
    liveConnected = false;
    $('screen').removeAttribute('src');
  }
  $('liveSwitch').textContent = wantLive ? 'Stop live' : 'Start live';
  $('liveState').textContent = liveConnected ? 'Live JPEG stream' : 'Snapshot mode';
  $('livePill').textContent = liveConnected ? 'LIVE' : 'PREVIEW';
  $('livePill').classList.toggle('is-paused', !liveConnected);
}
$('liveSwitch').addEventListener('click', () => { wantLive = !wantLive; syncLive(); if (!wantLive) refresh(); });
$('liveFps').addEventListener('change', () => {
  if (liveConnected) { liveConnected = false; $('screen').removeAttribute('src'); }
  syncLive();
});
$('screen').addEventListener('error', () => {
  if (!liveConnected) return;
  liveConnected = false;
  wantLive = false;
  syncLive();
  showStatus('Live stream unavailable; switched to snapshots');
  refresh();
});

function fileRow(file) {
  const li = document.createElement('li');
  li.className = 'file-item';
  const head = document.createElement('div');
  head.className = 'file-head';
  const name = document.createElement('span');
  name.className = 'file-name';
  name.textContent = file.name;
  const meta = document.createElement('span');
  meta.className = 'file-meta';
  const size = Number(file.size) || 0;
  meta.textContent = (size < 1024 ? (size + ' B') : ((size / 1024).toFixed(1) + ' KiB')) + ' · ' + file.state;
  head.append(name, meta);
  li.appendChild(head);
  if (file.state === 'ready' && /^[0-9a-f]{32}$/.test(file.id)) {
    const actions = document.createElement('div');
    actions.className = 'file-actions';
    if (file.direction === 'download') {
      const link = document.createElement('a');
      link.href = '/api/files/' + file.id;
      link.textContent = '↓ Save to device';
      link.setAttribute('aria-label', 'Save ' + file.name + ' to this device');
      actions.appendChild(link);
    } else {
      const attach = document.createElement('button');
      attach.type = 'button';
      attach.textContent = 'Attach to page';
      attach.addEventListener('click', () => execute('attach_file', {file_id:file.id, selector:$('fileSelector').value}));
      actions.appendChild(attach);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Remove';
    remove.addEventListener('click', async () => {
      try { await api('/api/files/' + file.id, {method:'DELETE',headers:{'X-STARS-BROWSER-UI':'1'}}); await listFiles(); }
      catch (err) { showStatus('File error: ' + err.message); }
    });
    actions.appendChild(remove);
    li.appendChild(actions);
  }
  return li;
}
async function listFiles() {
  try {
    const files = await (await api('/api/files')).json();
    $('files').replaceChildren(...files.map(fileRow));
    $('filesCount').textContent = String(files.length);
    if (!files.length) {
      const li = document.createElement('li');
      li.className = 'empty-files';
      li.textContent = 'No transfers yet. Downloads you make in the remote browser appear here.';
      $('files').appendChild(li);
    }
  } catch (err) { showStatus(`File error: ${err.message}`); }
}
$('refreshFiles').addEventListener('click', listFiles);
$('stageFile').addEventListener('click', async () => {
  const file = $('uploadFile').files[0];
  if (!file) { showStatus('Choose a file first'); return; }
  if (file.size > 16 * 1024 * 1024) { showStatus('File must be 16 MiB or smaller'); return; }
  const form = new FormData(); form.append('file', file, file.name);
  try {
    await api('/api/files/upload', {method:'POST',headers:{'X-STARS-BROWSER-UI':'1'},body:form});
    $('uploadFile').value = '';
    await listFiles();
    showStatus('Upload staged; choose Attach to page to fill the site file input');
  } catch (err) { showStatus(`Upload error: ${err.message}`); }
});

$('screen').addEventListener('click', event => {
  const r = $('screen').getBoundingClientRect();
  if (!r.width || !r.height) return;
  execute('click', { x: (event.clientX - r.left) * viewport.width / r.width,
                     y: (event.clientY - r.top) * viewport.height / r.height });
});
$('pageText').addEventListener('click', async () => {
  try { $('screenText').textContent = await (await api('/api/snapshot')).text(); $('textDialog').showModal(); }
  catch (err) { showStatus(`Error: ${err.message}`); }
});
$('closeText').addEventListener('click', () => $('textDialog').close());
async function grant(seconds) {
  try {
    await api('/api/grant', {method:'POST', headers:{'Content-Type':'application/json','X-STARS-BROWSER-UI':'1'},body:JSON.stringify({seconds})});
    await refresh();
  } catch(err) { showStatus(`Grant error: ${err.message}`); }
}
$('grant').addEventListener('click', () => grant(Number($('grantLength').value)));
$('revoke').addEventListener('click', () => grant(0));
function openPanel(id) {
  const panel = $(id);
  panel.open = true;
  panel.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}
$('jumpFiles').addEventListener('click', () => { openPanel('filesPanel'); listFiles(); });
$('jumpGrant').addEventListener('click', () => openPanel('accessPanel'));
$('filesPanel').addEventListener('toggle', () => { if ($('filesPanel').open) listFiles(); });
// Keep expanded transfers fresh without hammering the server when the phone is hidden.
setInterval(() => { if (!document.hidden && $('filesPanel').open) listFiles(); }, 15000);
// Only refresh when the phone is looking at the browser. No permanent rapid screenshot stream.
document.addEventListener('visibilitychange', () => { syncLive(); if(!document.hidden) refresh(); });
window.addEventListener('pagehide', () => { liveConnected=false; $('screen').removeAttribute('src'); if(previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); });
pollTimer = setInterval(refresh, 7000);
syncLive();
refresh();
listFiles();
