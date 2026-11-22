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
    $('grantStatus').textContent = data.mcp_grant_remaining ? `AI: ${data.mcp_grant_remaining}s` : 'AI: locked';
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
  } catch(err) { showStatus(`Error: ${err.message}`); }
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
  const name = document.createElement('span');
  name.textContent = `${file.name} · ${file.size} bytes · ${file.state}`;
  li.appendChild(name);
  if (file.state === 'ready' && /^[0-9a-f]{32}$/.test(file.id)) {
    if (file.direction === 'download') {
      const link = document.createElement('a'); link.href = `/api/files/${file.id}`; link.textContent = 'Save'; li.appendChild(link);
    } else {
      const attach = document.createElement('button'); attach.textContent = 'Attach to page';
      attach.addEventListener('click', () => execute('attach_file', {file_id:file.id, selector:$('fileSelector').value}));
      li.appendChild(attach);
    }
    const remove = document.createElement('button'); remove.textContent = 'Remove';
    remove.addEventListener('click', async () => {
      try { await api(`/api/files/${file.id}`, {method:'DELETE',headers:{'X-STARS-BROWSER-UI':'1'}}); await listFiles(); }
      catch (err) { showStatus(`File error: ${err.message}`); }
    });
    li.appendChild(remove);
  }
  return li;
}
async function listFiles() {
  try {
    const files = await (await api('/api/files')).json();
    $('files').replaceChildren(...files.map(fileRow));
    if (!files.length) { const li=document.createElement('li');li.textContent='No staged files';$('files').appendChild(li); }
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
// Only refresh when the phone is looking at the browser. No permanent rapid screenshot stream.
document.addEventListener('visibilitychange', () => { syncLive(); if(!document.hidden) refresh(); });
window.addEventListener('pagehide', () => { liveConnected=false; $('screen').removeAttribute('src'); if(previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); });
pollTimer = setInterval(refresh, 7000);
syncLive();
refresh();
listFiles();
