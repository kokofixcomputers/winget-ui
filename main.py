import webview
import subprocess
import threading
import signal
import time
import json
import uuid


def clean_and_split_winget_output(lines):
    cleaned_lines = []
    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped or set(stripped) <= {'-'}:
            continue
        if stripped.startswith('Name') and 'Id' in stripped and 'Version' in stripped and 'Source' in stripped:
            header_found = True
            continue
        if not header_found:
            continue
        cleaned_lines.append(line.strip())
    results = []
    for line in cleaned_lines:
        parts = line.split()
        if len(parts) <= 4:
            results.append(parts)
        else:
            name = ' '.join(parts[:-3])
            rest = parts[-3:]
            results.append([name] + rest)
    return results


def clean_and_split_winget_upgrade_output(lines):
    cleaned_lines = []
    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped or set(stripped) <= {'-'}:
            continue
        if stripped.startswith('Name') and 'Id' in stripped and 'Version' in stripped and 'Available' in stripped and 'Source' in stripped:
            header_found = True
            continue
        if not header_found:
            continue
        cleaned_lines.append(line.strip())
    results = []
    for line in cleaned_lines:
        parts = line.split()
        if len(parts) <= 5:
            results.append(parts)
        else:
            name = ' '.join(parts[:-4])
            rest = parts[-4:]
            results.append([name] + rest)
    print(results)
    return results


def parse_winget_show_output(text):
    info = {}
    current_key = None
    current_value_lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if ':' in line:
            if current_key:
                info[current_key] = '\n'.join(current_value_lines).strip()
            key, val = line.split(':', 1)
            current_key = key.strip()
            current_value_lines = [val.strip()]
        else:
            current_value_lines.append(line.strip())
    if current_key:
        info[current_key] = '\n'.join(current_value_lines).strip()
    return info


html_code = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Winget GUI - Complete</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .scrollbar-thin::-webkit-scrollbar {
      width: 8px; height:8px;
    }
    .scrollbar-thin::-webkit-scrollbar-thumb {
      background-color: #a0aec0; border-radius: 4px;
    }
    #sidebarLogs, #errorLog {
      user-select: text;
      -webkit-user-select: text;
      -moz-user-select: text;
      -ms-user-select: text;
    }
    @keyframes stripes {
      0% {background-position: 1rem 0}
      100% {background-position: 0 0}
    }
    .animated-stripes {
      background-image: linear-gradient(
        45deg,
        rgba(255,255,255,.15) 25%,
        transparent 25%,
        transparent 50%,
        rgba(255,255,255,.15) 50%,
        rgba(255,255,255,.15) 75%,
        transparent 75%,
        transparent
      );
      background-size: 1rem 1rem;
      animation: stripes 1s linear infinite;
    }
    .copy-button {
      background-color: #3b82f6;
      color: white;
      border-radius: 4px;
      padding: 0 6px;
      cursor: pointer;
      font-size: 0.75em;
      margin-left: 8px;
      user-select: none;
    }
    .copy-button:hover {
      background-color: #2563eb;
    }
  </style>
</head>

<body class="bg-gray-100 min-h-screen flex" oncontextmenu="return false;">
<!-- Details Modal -->
<div id="detailModal" class="hidden fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
  <div class="bg-white rounded-lg shadow-lg max-w-xl w-full p-6 relative">
    <h2 class="text-xl font-semibold mb-4">Package Details</h2>
    <div id="detailContent" class="max-h-96 overflow-y-auto text-sm space-y-2"></div>
    <div class="mt-4 flex justify-end">
      <button onclick="closeDetailModal()" class="bg-gray-600 hover:bg-gray-700 text-white py-1 px-4 rounded">Close</button>
    </div>
  </div>
</div>

  <div class="w-64 bg-white shadow-lg flex flex-col sticky top-0 h-screen overflow-auto">
    <h2 class="text-xl font-semibold p-4 border-b border-gray-200">Winget GUI</h2>
    <nav class="flex flex-col flex-grow p-2 space-y-1">
      <button id="tabSearch" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200 font-semibold text-indigo-600">Search</button>
      <button id="tabPackages" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Packages</button>
      <button id="tabTasks" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Tasks</button>
      <button id="tabUpdates" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Updates</button>
      <button id="tabSources" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Sources</button>
    </nav>
    <div id="sidebarLogs" class="p-4 border-t border-gray-200 text-xs font-mono h-48 overflow-y-auto scrollbar-thin whitespace-pre"></div>
  </div>

  <div class="flex-1 p-6 overflow-auto max-h-screen">
    <!-- Search Panel -->
    <div id="searchContent" class="">
      <div class="max-w-4xl mx-auto">
        <div class="flex space-x-2 mb-6">
          <input id="searchBox" type="search" placeholder="Search for apps..."
            class="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500" oninput="searchFilter()"/>
          <button onclick="doSearch()"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-md transition">Search</button>
        </div>
        <div class="flex mb-4">
          <button onclick="installSelected()" class="bg-indigo-600 text-white px-3 py-1 rounded mr-2">Install Selected</button>
        </div>
        <div id="resultsGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
      </div>
    </div>

    <!-- Packages Panel -->
    <div id="packagesContent" class="hidden max-w-4xl mx-auto">
      <div class="flex mb-2">
        <button onclick="uninstallSelected()" class="bg-red-600 text-white px-3 py-1 rounded">Uninstall Selected</button>
      </div>
      <input id="packageSearchBox" oninput="filterInstalledPackages()" placeholder="Search installed packages..."
        class="mb-4 px-3 py-2 border border-gray-300 rounded w-full" type="search" />
      <h2 class="text-xl font-semibold mb-4">Installed Packages</h2>
      <div id="installedGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
    </div>

    <!-- Tasks Panel -->
    <div id="tasksContent" class="hidden max-w-4xl mx-auto">
      <h2 class="text-xl font-semibold mb-4">Tasks</h2>
      <div id="tasksGrid" class="space-y-4"></div>
    </div>

    <!-- Updates Panel -->
    <div id="updatesContent" class="hidden max-w-4xl mx-auto">
      <div class="max-w-4xl mx-auto">
        <div class="flex space-x-2 mb-6">
          <input id="updateSearchBox" type="search" placeholder="Search available updates..."
            class="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500" oninput="filterUpdates()" />
          <button onclick="loadAvailableUpdates()"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded ml-2 transition">Refresh</button>
        </div>
        <div class="flex mb-4">
          <button onclick="upgradeSelected()" class="bg-indigo-600 text-white px-3 py-1 rounded mr-2">Upgrade Selected</button>
        </div>
        <div id="updatesGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
      </div>
    </div>

    <!-- Sources Panel -->
    <div id="sourcesContent" class="hidden max-w-4xl mx-auto">
      <div class="flex space-x-2 mb-4">
        <input id="sourceName" type="text" placeholder="Source name" class="px-2 py-1 border rounded w-32" />
        <input id="sourceArg" type="text" placeholder="Source URL/Path" class="px-2 py-1 border rounded w-64" />
        <input id="sourceType" type="text" placeholder="(Optional) Type" class="px-2 py-1 border rounded w-32" />
        <button onclick="handleSourceForm()" id="sourceFormBtn" class="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded">Add</button>
        <button onclick="resetSourceForm()" id="sourceResetBtn" class="bg-gray-400 hover:bg-gray-600 text-white px-3 py-1 rounded hidden">Cancel Edit</button>
      </div>
      <h2 class="text-xl font-semibold mb-4">Sources</h2>
      <div id="sourcesGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
    </div>
  </div>

<script>
let installedIds = new Set();
let tasks = {};
let editingSourceOrigName = null;
let allUpdates = [];

const tabs = {
  search: document.getElementById('tabSearch'),
  packages: document.getElementById('tabPackages'),
  tasks: document.getElementById('tabTasks'),
  updates: document.getElementById('tabUpdates'),
  sources: document.getElementById('tabSources')
};
const contents = {
  search: document.getElementById('searchContent'),
  packages: document.getElementById('packagesContent'),
  tasks: document.getElementById('tasksContent'),
  updates: document.getElementById('updatesContent'),
  sources: document.getElementById('sourcesContent')
};

const sidebarLogs = document.getElementById('sidebarLogs');

tabs.search.addEventListener('click', ()=>switchTab('search'));
tabs.packages.addEventListener('click', ()=>switchTab('packages'));
tabs.tasks.addEventListener('click', ()=>switchTab('tasks'));
tabs.updates.addEventListener('click', () => {switchTab('updates'); loadAvailableUpdates();});
tabs.sources.addEventListener('click', ()=>switchTab('sources'));

function switchTab(tabKey){
  Object.keys(tabs).forEach(k=>{
    if(k===tabKey){
      tabs[k].classList.add('font-semibold', 'text-indigo-600');
      contents[k].classList.remove('hidden');
    }else{
      tabs[k].classList.remove('font-semibold', 'text-indigo-600');
      contents[k].classList.add('hidden');
    }
  });
  if(tabKey==='packages'){
    loadInstalledPackages();
  }
  if(tabKey==='tasks'){
    renderTasks();
  }
  if(tabKey==='sources'){
    loadSources();
    resetSourceForm();
  }
}

function addTask(id, type, pkgid){
  tasks[id] = {id:id, type:type, pkgid:pkgid, status:'running', message:'', progress:0, procExist:true};
  renderTasks();
}
function completeTask(id){
  if (!tasks[id]) return;
  tasks[id].status = 'success';
  tasks[id].progress = 100;
  tasks[id].procExist = false;
  renderTasks();
  refreshPackagesAfterTask(tasks[id].type, tasks[id].pkgid);
}
function refreshPackagesAfterTask(taskType, pkgid){
  window.pywebview.api.winget_list_installed().then(raw=>{
    let results = [];
    try{
      results = JSON.parse(raw);
      installedIds = new Set(results.map(r=>r[1]));
      renderInstalledPackages(results);
      if(contents['search'].classList.contains('hidden')===false){
        doSearch();
      }
    }catch(e){}
  });
}
function renderTasks() {
  const container = document.getElementById('tasksGrid');
  container.innerHTML = '';
  Object.values(tasks).forEach(task=>{
    const bars = 'overflow-hidden h-2 mb-2 text-xs flex rounded';
    const barColor = task.status === 'error'
      ? 'bg-red-200'
      : task.status === 'success'
        ? 'bg-green-200'
        : 'bg-indigo-200';

    const fillBase = 'shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center transition-all duration-500';
    const fillColor = task.status === 'error'
      ? 'bg-red-600'
      : task.status === 'success'
        ? 'bg-green-600'
        : 'bg-indigo-500';

    const errorMsg = task.status === 'error' ? '<div class="text-red-600 font-semibold mb-2">Error occurred</div>' : '';
    const cancelDisabled = !task.procExist ? 'disabled' : '';
    let width = Math.min(task.progress ? task.progress : 0, 100);

    let indCls = '';
    if (task.status === 'running') {
      indCls = 'animated-stripes';
    }

    const html = `<div class="p-4 bg-white rounded-lg shadow flex flex-col" id="task-${task.id}">
      <div class="flex justify-between items-center mb-2 text-sm">
        <div><strong>${task.type.toUpperCase()}</strong> ${task.pkgid}</div>
        <div>
          <button onclick="cancelTask('${task.id}')" ${cancelDisabled} class="bg-red-500 hover:bg-red-700 disabled:opacity-50 text-white px-3 py-1 rounded mr-2">Cancel</button>
          <button onclick="clearTask('${task.id}')" class="bg-gray-500 hover:bg-gray-700 text-white px-3 py-1 rounded">Clear</button>
        </div>
      </div>
      ${errorMsg}
      <div class="${bars} ${barColor}">
        <div class="${fillBase} ${fillColor} ${indCls}" style="width:${width}%"></div>
      </div>
      <pre class="text-xs font-mono whitespace-pre-wrap max-h-32 overflow-auto">${task.message}</pre>
    </div>`;
  container.insertAdjacentHTML('beforeend', html);
  const logEl = container.querySelector(`#task-${task.id} pre`);
  if (logEl) { logEl.scrollTop = logEl.scrollHeight; }
  });
}

function updateTask(id, message, error = false, success = true) {
  if (!tasks[id]) return;
  tasks[id].message += message + '\n';
  if (error) tasks[id].status = 'error';
  renderTasks();
}
function appendLog(line){
  sidebarLogs.textContent += line + "\n";
  sidebarLogs.scrollTop = sidebarLogs.scrollHeight;
  Object.values(tasks).forEach(task=>{
    if(task.status==='running'){
      task.message += line + "\n";
    }
  });
  renderTasks();
}

function cancelTask(id){
  if(!tasks[id]) return;
  if(tasks[id].procExist){
    window.pywebview.api.cancel_task(id);
  }
  tasks[id].status='cancelled';
  tasks[id].procExist = false;
  renderTasks();
}

function clearTask(id){
  if(!tasks[id]) return;
  delete tasks[id];
  renderTasks();
}

async function doSearch(){
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  if(!q) return;
  const container = document.getElementById('resultsGrid');
  container.innerHTML = '<div class="text-gray-500 italic">Searching...</div>';
  try {
    const raw = await window.pywebview.api.winget_search(q);
    let results = [];
    try {
      results = JSON.parse(raw);
    } catch(e) {
      showErrorPopup('Search parse error: '+e.message);
      return;
    }
    renderSearchResults(results);
  } catch(e) {
    container.innerHTML = '<div class="text-red-600">Search failed: ' + e.message + '</div>';
  }
}

function searchFilter() {
  const filter = document.getElementById('searchBox').value.toLowerCase();
  const container = document.getElementById('resultsGrid');
  Array.from(container.children).forEach(card=>{
    const nameSpan = card.querySelector('label span.font-medium');
    if(!nameSpan) return;
    const text = nameSpan.textContent.toLowerCase();
    card.style.display = text.includes(filter) ? "" : "none";
  });
}

function renderSearchResults(results){
  const container = document.getElementById('resultsGrid');
  container.innerHTML = '';
  if(!results.length){
    container.innerHTML = '<div class="text-gray-500 italic">No results found.</div>';
    return;
  }
  results.forEach(pkg=>{
    const isInstalled = installedIds.has(pkg[1]);
    const btnLabel = isInstalled ? 'Uninstall' : 'Install';
    const btnClass = isInstalled ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700';
    const onClickFunc = isInstalled ? `doUninstall('${pkg[1]}')` : `doInstall('${pkg[1]}')`;
    const card = document.createElement('div');
    card.className = 'p-5 bg-gray-50 border border-gray-300 rounded-lg shadow flex flex-col';
    card.innerHTML = `
      <label class="inline-flex items-center space-x-2 mb-2">
        <input type="checkbox" class="pkgCheckbox form-checkbox h-5 w-5 text-indigo-600" value="${pkg[1]}" />
        <span class="font-medium">${pkg[0]}</span>
      </label>
      <div class="text-sm text-gray-500 mb-1">ID: ${pkg[1]}</div>
      <div class="text-xs mb-1">Version: ${pkg[2]}</div>
      <div class="text-xs mb-3">Source: ${pkg[3]}</div>
      <div class="flex space-x-2 mt-auto">
        <button class="${btnClass} text-white py-1 px-3 rounded transition" onclick="${onClickFunc}">${btnLabel}</button>
        <button class="bg-gray-300 hover:bg-gray-400 text-gray-700 py-1 px-3 rounded transition" onclick="showPackageDetails('${pkg[1]}')">Details</button>
      </div>`;
    container.appendChild(card);
  });
}

async function loadInstalledPackages(){
  const container = document.getElementById('installedGrid');
  container.innerHTML = '<div class="text-gray-500 italic">Loading installed packages...</div>';
  const raw = await window.pywebview.api.winget_list_installed();
  let results = [];
  try {
    results = JSON.parse(raw);
  } catch (e){
    showErrorPopup('Installed packages parse error: ' + e.message + "\n" + raw);
    return;
  }
  installedIds = new Set(results.map(r => r[1]));
  renderInstalledPackages(results);
}

function filterInstalledPackages(){
  const filter = document.getElementById('packageSearchBox').value.toLowerCase();
  const container = document.getElementById('installedGrid');
  Array.from(container.children).forEach(card=>{
    const text = card.innerText.toLowerCase();
    card.style.display = text.includes(filter) ? "" : "none";
  });
}

function renderInstalledPackages(packages){
  const container = document.getElementById('installedGrid');
  container.innerHTML = '';
  if(!packages.length){
    container.innerHTML = '<div class="text-gray-500 italic">No installed packages found.</div>';
    return;
  }
  packages.forEach(pkg=>{
    const card = document.createElement('div');
    card.className = 'p-5 bg-white border border-gray-300 rounded-lg shadow flex flex-col';
    card.innerHTML = `
      <input type="checkbox" class="installedPkgCheckbox" value="${pkg[1]}" />
      <div class="font-bold text-lg mb-2">${pkg[0]}</div>
      <div class="text-sm text-gray-500 mb-1">ID: ${pkg[1]}</div>
      <div class="text-xs mb-1">Version: ${pkg[2]}</div>
      <div class="text-xs mb-3">Source: ${pkg[3]}</div>
      <div class="flex space-x-2 mt-auto">
        <button class="bg-red-600 hover:bg-red-700 text-white py-1 px-3 rounded transition" onclick="doUninstall('${pkg[1]}')">Uninstall</button>
        <button class="bg-gray-300 hover:bg-gray-400 text-gray-700 py-1 px-3 rounded transition" onclick="showPackageDetails('${pkg[1]}')">Details</button>
      </div>`;
    container.appendChild(card);
  });
}

async function doInstall(pkgid){
  await window.pywebview.api.winget_install(pkgid);
}

async function doUninstall(pkgid){
  await window.pywebview.api.winget_uninstall(pkgid);
}

async function installSelected(){
  const checkboxes = document.querySelectorAll('#resultsGrid .pkgCheckbox:checked');
  const ids = Array.from(checkboxes).map(cb => cb.value);
  for(const id of ids){
    await doInstall(id);
  }
}

async function uninstallSelected(){
  const checkboxes = document.querySelectorAll('#installedGrid .installedPkgCheckbox:checked');
  const ids = Array.from(checkboxes).map(cb => cb.value);
  for(const id of ids){
    await doUninstall(id);
  }
}

async function loadAvailableUpdates(){
  const container = document.getElementById('updatesGrid');
  container.innerHTML = '<div class="text-gray-500 italic">Checking for updates...</div>';
  try {
    const raw = await window.pywebview.api.winget_upgrade_list();
    let results = [];
    try {
      results = JSON.parse(raw);
      allUpdates = results;
    } catch(e){
      showErrorPopup('Update list parse error: ' + e.message);
      container.innerHTML = '<div class="text-red-600">Failed to parse update data.</div>';
      return;
    }
    renderUpdateResults(results);
  } catch(e){
    container.innerHTML = '<div class="text-red-600">Failed to load updates: ' + e.message + '</div>';
  }
}

function renderUpdateResults(results){
  const container = document.getElementById('updatesGrid');
  container.innerHTML = '';
  if(!results.length){
    container.innerHTML = '<div class="text-gray-500 italic">No updates available.</div>';
    return;
  }
  results.forEach(pkg=>{
    const card = document.createElement('div');
    card.className = 'p-5 bg-gray-50 border border-gray-300 rounded-lg shadow flex flex-col';
    card.innerHTML = `
      <label class="inline-flex items-center space-x-2 mb-2">
        <input type="checkbox" class="updateCheckbox form-checkbox h-5 w-5 text-indigo-600" value="${pkg[1]}" />
        <span class="font-medium">${pkg[0]}</span>
      </label>
      <div class="text-sm text-gray-500 mb-1">Current Version: ${pkg[2]}</div>
      <div class="text-xs mb-3">Available Version: ${pkg[3]}</div>
      <div class="text-xs mb-3">Source: ${pkg[4]}</div>
      <div class="flex space-x-2 mt-auto">
        <button class="bg-indigo-600 hover:bg-indigo-700 text-white py-1 px-3 rounded transition" onclick="doUpgrade('${pkg[1]}')">Upgrade</button>
      </div>`;
    container.appendChild(card);
  });
}

function filterUpdates(){
  const filter = document.getElementById('updateSearchBox').value.toLowerCase();
  const filtered = allUpdates.filter(pkg => (pkg[0]).toLowerCase().includes(filter));
  renderUpdateResults(filtered);
}

async function doUpgrade(pkgid){
  await window.pywebview.api.winget_upgrade(pkgid);
  loadAvailableUpdates();
}

async function upgradeSelected(){
  const checkboxes = document.querySelectorAll('#updatesGrid .updateCheckbox:checked');
  const ids = Array.from(checkboxes).map(cb => cb.value);
  for(const id of ids){
    await doUpgrade(id);
  }
  loadAvailableUpdates();
}

async function showPackageDetails(pkgid){
  const modal = document.getElementById('detailModal');
  const content = document.getElementById('detailContent');
  content.textContent = 'Loading package details...';
  modal.classList.remove('hidden');
  try{
    const raw = await window.pywebview.api.winget_show(pkgid);
    let info = {};
    try{
      info = JSON.parse(raw);
    }catch(e){
      info = {error: raw};
    }
    content.innerHTML = renderDetailsHtml(info);
  }catch(e){
    content.textContent = 'Failed to load details: ' + e.message;
  }
}

function closeDetailModal(){
  document.getElementById('detailModal').classList.add('hidden');
  document.getElementById('detailContent').textContent = '';
}

function renderDetailsHtml(info){
  if(info.error) return `<div class="text-red-600 font-semibold">Error: ${htmlEscape(info.error)}</div>`;
  function createCopyButton(value){
    return `<button class="copy-button" onclick="copyToClipboard('${htmlEscape(value)}')">Copy</button>`;
  }
  const keysToShow = ['Id','Version','Description','Installer Url','Homepage','Publisher','Publisher Url','License','License Url','Privacy Url','Release Notes','Publisher Support Url','Purchase Url'];
  let htmlStr = '';
  for(let key of keysToShow){
    if(info[key]){
      htmlStr += `<div><strong>${htmlEscape(key)}:</strong> ${htmlEscape(info[key])} ${createCopyButton(info[key])}</div>`;
    }
  }
  return htmlStr || '<div>No detailed info available.</div>';
}

function copyToClipboard(text){
  navigator.clipboard.writeText(text).then(()=>alert('Copied to clipboard!'), ()=>alert('Failed to copy!'));
}

function htmlEscape(text){
  return text.replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];});
}

async function loadSources(){
  const raw = await window.pywebview.api.winget_list_sources();
  let results = [];
  try {
    results = JSON.parse(raw);
  } catch(e) {
    showErrorPopup('Source list parse error: ' + e.message + '\n' + raw);
    return;
  }
  renderSources(results);
}

function renderSources(sources){
  const container = document.getElementById('sourcesGrid');
  container.innerHTML = '';
  if(!sources.length){
    container.innerHTML = '<div class="text-gray-500 italic">No sources found.</div>';
    return;
  }
  sources.forEach(src => {
    const card = document.createElement('div');
    card.className = 'p-5 bg-white border border-gray-300 rounded-lg shadow flex flex-col';
    card.innerHTML = `
      <div class="font-bold text-lg mb-1">${src.Name}</div>
      <div class="text-xs mb-1"><b>Type:</b> ${src.Type || ""}</div>
      <div class="text-xs mb-1"><b>URL:</b> ${src.Arg || ""}</div>
      <div class="flex space-x-2 mt-4">
        <button class="bg-red-600 hover:bg-red-700 text-white py-1 px-2 rounded transition" onclick="deleteSource('${src.Name}')">Delete</button>
        <button class="bg-indigo-600 hover:bg-indigo-700 text-white py-1 px-2 rounded transition" onclick="editSourcePrompt('${src.Name}','${src.Arg}','${src.Type || ""}')">Edit</button>
      </div>`;
    container.appendChild(card);
  });
}

async function handleSourceForm() {
  const name = document.getElementById('sourceName').value.trim();
  const arg = document.getElementById('sourceArg').value.trim();
  const typ = document.getElementById('sourceType').value.trim();
  if (!name || !arg) return;
  if(editingSourceOrigName && editingSourceOrigName !== name)
    await window.pywebview.api.winget_delete_source(editingSourceOrigName);
  if(editingSourceOrigName) {
    await window.pywebview.api.winget_delete_source(name);
  }
  await window.pywebview.api.winget_add_source(name, arg, typ);
  await loadSources();
  resetSourceForm();
}
window.handleSourceForm = handleSourceForm;

async function deleteSource(name){
  if(!confirm(`Are you sure you want to delete source '${name}'?`)) return;
  await window.pywebview.api.winget_delete_source(name);
  loadSources();
}
window.deleteSource = deleteSource;

function editSourcePrompt(name,arg,typ){
  document.getElementById('sourceName').value = name;
  document.getElementById('sourceArg').value = arg;
  document.getElementById('sourceType').value = typ;
  editingSourceOrigName = name;
  document.getElementById('sourceFormBtn').textContent = "Save";
  document.getElementById('sourceResetBtn').classList.remove('hidden');
}
window.editSourcePrompt = editSourcePrompt;

function resetSourceForm(){
  document.getElementById('sourceName').value = "";
  document.getElementById('sourceArg').value = "";
  document.getElementById('sourceType').value = "";
  document.getElementById('sourceFormBtn').textContent = "Add";
  document.getElementById('sourceResetBtn').classList.add('hidden');
  editingSourceOrigName = null;
}
window.resetSourceForm = resetSourceForm;

function showErrorPopup(msg) {
  alert(msg);
}

</script>

</body>
</html>
"""


class Api:
    def __init__(self):
        self.window = None
        self.tasks = {}
        self.procs = {}

    def set_window(self, window):
        self.window = window

    def clean_and_split_winget_output(self, lines):
        return clean_and_split_winget_output(lines)

    def clean_and_split_winget_upgrade_output(self, lines):
        return clean_and_split_winget_upgrade_output(lines)

    def winget_search(self, query):
        if not query:
            return "[]"
        try:
            completed = subprocess.run(
                ["winget", "search", query],
                capture_output=True,
                text=True,
                shell=True,
            )
            lines = completed.stdout.splitlines()
            parsed = self.clean_and_split_winget_output(lines)
            return json.dumps(parsed)
        except Exception as e:
            self.show_error(str(e))
            return json.dumps([{"error": str(e)}])

    def winget_list_installed(self):
        try:
            completed = subprocess.run(
                ["winget", "list"],
                capture_output=True,
                text=True,
                shell=True,
            )
            lines = completed.stdout.splitlines()
            parsed = self.clean_and_split_winget_output(lines)
            return json.dumps(parsed)
        except Exception as e:
            self.show_error(str(e))
            return json.dumps([{"error": str(e)}])

    def winget_show(self, pkgid):
        try:
            completed = subprocess.run(
                ["winget", "show", "--id", pkgid],
                capture_output=True,
                text=True,
                shell=True,
            )
            info = parse_winget_show_output(completed.stdout)
            return json.dumps(info)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def winget_upgrade_list(self):
        try:
            completed = subprocess.run(
                ["winget", "upgrade", "--accept-source-agreements"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
            )
            print(completed.stdout)
            if completed.returncode != 0:
                return json.dumps([])
            lines = completed.stdout.splitlines()
            print(lines)
            parsed = self.clean_and_split_winget_upgrade_output(lines)
            return json.dumps(parsed)
        except Exception as e:
            self.show_error(str(e))
            return json.dumps([])

    def winget_install(self, pkgid):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"type": "install", "pkgid": pkgid, "status": "running", "message": "", "procExist": True}
        if self.window:
            self.window.evaluate_js(f"appendLog('Started install task {task_id} for {pkgid}')")
            self.window.evaluate_js(f"addTask('{task_id}', 'install', '{pkgid}')")

        proc = subprocess.Popen(
            [
                "winget",
                "install",
                "-e",
                "--id",
                pkgid,
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.procs[task_id] = proc
        threading.Thread(target=self.collect_output, args=(task_id, proc), daemon=True).start()
        return True

    def winget_uninstall(self, pkgid):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"type": "uninstall", "pkgid": pkgid, "status": "running", "message": "", "procExist": True}
        if self.window:
            self.window.evaluate_js(f"appendLog('Started uninstall task {task_id} for {pkgid}')")
            self.window.evaluate_js(f"addTask('{task_id}', 'uninstall', '{pkgid}')")

        proc = subprocess.Popen(
            [
                "winget",
                "uninstall",
                "--id",
                pkgid,
                "--accept-source-agreements",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.procs[task_id] = proc
        threading.Thread(target=self.collect_output, args=(task_id, proc), daemon=True).start()
        return True
    
    def collect_output(self, task_id, proc):
      keywords = ['fail', 'cannot find', 'error', 'no installed package found']
      error_output = []
      error_detected = False
      try:
          for line in iter(proc.stdout.readline, ""):
              if not line:
                  break
              if self.window:
                  escaped_line = json.dumps(line.strip())
                  if escaped_line.strip() and not "-" in escaped_line.strip() and not escaped_line.strip() == " ":
                      print(str(escaped_line.strip()))
                      self.window.evaluate_js(f"appendLog({escaped_line})")

                  lower_line = line.lower()
                  is_error_line = any(k in lower_line for k in keywords)
                  if is_error_line:
                      error_detected = True
                      error_output.append(line.strip())

                  self.window.evaluate_js(f"updateTask('{task_id}', {escaped_line}, {str(is_error_line).lower()})")

          proc.stdout.close()
          proc.wait()

          if error_detected:
              error_message = "\n".join(error_output)
              self.window.evaluate_js(f"updateTask('{task_id}', 'Error occurred', true, false)")
              self.show_error(error_message)
          else:
              self.window.evaluate_js(f"completeTask('{task_id}')")
              self.window.evaluate_js(f"updateTask('{task_id}', 'Task completed successfully', false, true)")
              self.window.evaluate_js(f"appendLog('Task process ended successfully.')")
      except Exception as e:
          self.window.evaluate_js(f"updateTask('{task_id}', 'Exception occurred: {json.dumps(str(e))}', true, false)")
          self.show_error(f"Exception occurred: {str(e)}")


    def winget_upgrade(self, pkgid):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"type": "upgrade", "pkgid": pkgid, "status": "running", "message": "", "procExist": True}
        if self.window:
            self.window.evaluate_js(f"appendLog('Started upgrade task {task_id} for {pkgid}')")
            self.window.evaluate_js(f"addTask('{task_id}', 'upgrade', '{pkgid}')")

        proc = subprocess.Popen(
            [
                "winget",
                "upgrade",
                "-e",
                "--id",
                pkgid,
                "--accept-source-agreements",
                "--accept-package-agreements",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self.procs[task_id] = proc
        threading.Thread(target=self.collect_output, args=(task_id, proc), daemon=True).start()
        return True

    def winget_list_sources(self):
        try:
            completed = subprocess.run(
                ["winget", "source", "list"],
                capture_output=True,
                text=True,
                shell=True,
            )
            lines = completed.stdout.splitlines()
            sources = []
            for line in lines:
                if not line.strip() or set(line.strip()) <= {"-"} or line.strip().startswith("Name "):
                    continue
                parts = line.strip().split()
                if len(parts) >= 2:
                    source = {"Name": parts[0], "Arg": parts[1]}
                    if len(parts) > 2:
                        source["Type"] = parts[2]
                    else:
                        source["Type"] = ""
                    sources.append(source)
            return json.dumps(sources)
        except Exception as e:
            self.show_error(str(e))
            return json.dumps([])

    def winget_add_source(self, name, arg, typ=""):
        try:
            cmd = [
                "winget", "source", "add",
                "--name", name,
                arg,
                "--accept-source-agreements"
            ]
            if typ:
                cmd += ["--type", typ]
            completed = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            return completed.stdout
        except Exception as e:
            self.show_error(str(e))
            return str(e)

    def winget_delete_source(self, name):
        try:
            cmd = ["winget", "source", "remove", "--name", name, "--accept-source-agreements"]
            completed = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            return completed.stdout
        except Exception as e:
            self.show_error(str(e))
            return str(e)

    def cancel_task(self, task_id):
        proc = self.procs.get(task_id)
        if not proc:
            return False
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            t_wait = 6
            for _ in range(t_wait * 10):
                if proc.poll() is not None:
                    return True
                time.sleep(0.1)
            if proc.poll() is None:
                proc.terminate()
            return True
        except Exception as e:
            print(f"Failed to cancel task {task_id}: {e}")
            return False

    def show_error(self, message):
        if self.window:
            escaped = json.dumps(message)
            self.window.evaluate_js(f"showErrorPopup({escaped})")


if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "Winget GUI - Complete",
        html=html_code,
        js_api=api,
        width=1300,
        height=800,
    )
    api.set_window(window)
    webview.start(debug=True)
