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
      width: 8px; height: 8px;
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

  <div class="w-64 bg-white shadow-lg flex flex-col sticky top-0 h-screen overflow-auto">
    <h2 class="text-xl font-semibold p-4 border-b border-gray-200">Winget GUI</h2>
    <nav class="flex flex-col flex-grow p-2 space-y-1">
      <button id="tabSearch" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200 font-semibold text-indigo-600">Search</button>
      <button id="tabPackages" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Packages</button>
      <button id="tabTasks" class="text-left px-4 py-2 rounded hover:bg-indigo-100 focus:outline-none focus:bg-indigo-200">Tasks</button>
    </nav>
    <div id="sidebarLogs" class="p-4 border-t border-gray-200 text-xs font-mono h-48 overflow-y-auto scrollbar-thin whitespace-pre"></div>
  </div>

  <div class="flex-1 p-6 overflow-auto max-h-screen">
    <!-- Search Panel -->
    <div id="searchContent" class="">
      <div class="max-w-4xl mx-auto">
        <div class="flex space-x-2 mb-6">
          <input id="searchBox" type="text" placeholder="Search for apps..."
            class="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"/>
          <button onclick="doSearch()"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-md transition">Search</button>
        </div>
        <div id="resultsGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
      </div>
    </div>

    <!-- Packages Panel -->
    <div id="packagesContent" class="hidden max-w-4xl mx-auto">
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
  </div>

  <!-- Error Modal -->
  <div id="errorModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden z-50">
    <div class="bg-white rounded-lg shadow-lg max-w-2xl w-full p-6 mx-4">
      <h3 class="text-xl font-semibold mb-4 text-red-600">Error</h3>
      <pre id="errorLog" class="bg-gray-100 p-4 rounded text-xs font-mono max-h-64 overflow-auto whitespace-pre-wrap"></pre>
      <div class="mt-4 flex justify-end">
        <button onclick="closeErrorModal()" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md transition">Close</button>
      </div>
    </div>
  </div>

  <!-- Package Detail Modal -->
  <div id="detailModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden z-50">
    <div class="bg-white rounded-lg shadow-lg max-w-3xl w-full p-6 mx-4 overflow-auto max-h-[80vh]">
      <h3 class="text-xl font-semibold mb-4">Package Details</h3>
      <button onclick="closeDetailModal()" class="float-right text-gray-500 hover:text-gray-700 mb-4">✖</button>
      <div id="detailContent" class="text-sm whitespace-pre-wrap font-mono"></div>
    </div>
  </div>

<script>
let installedIds = new Set();
let tasks = {};

const tabs = { search: document.getElementById('tabSearch'),
               packages: document.getElementById('tabPackages'),
               tasks: document.getElementById('tabTasks') };
const contents = { search: document.getElementById('searchContent'),
                  packages: document.getElementById('packagesContent'),
                  tasks: document.getElementById('tasksContent') };
const sidebarLogs = document.getElementById('sidebarLogs');
const errorModal = document.getElementById('errorModal');
const errorLog = document.getElementById('errorLog');

function addTask(id, type, pkgid){
  tasks[id] = {id:type, type:type, pkgid:pkgid, status:'running', message:'', progress:0, procExist:true};
  renderTasks();
}

function renderTasks() {
  const container = document.getElementById('tasksGrid');
  container.innerHTML = '';
  Object.values(tasks).forEach(task=>{
    const bars = 'overflow-hidden h-2 mb-2 text-xs flex rounded';
    const barColor = task.status === 'error' ? 'bg-red-500' : 'bg-indigo-200';
    const fillBase = 'shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center transition-all duration-500';
    const fillColor = task.status === 'error' ? 'bg-red-700' :
                  task.status === 'success' ? 'bg-green-600' : 'bg-green-600';
    const errorMsg = task.status === 'error' ? '<div class="text-red-600 font-semibold mb-2">Error occurred</div>' : '';
    const cancelDisabled = !task.procExist ? 'disabled' : '';
    let width = Math.min(task.progress ? task.progress : 0, 100);

    let indCls = '';
    if (task.status === 'running' && width === 0) {
      indCls = task.status === 'error' ? '' : ' animated-stripes bg-indigo-500';
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
  });
}

function updateTask(id, message, error=false, success=true) {
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
}

tabs.search.addEventListener('click', ()=>switchTab('search'));
tabs.packages.addEventListener('click', ()=>switchTab('packages'));
tabs.tasks.addEventListener('click', ()=>switchTab('tasks'));
switchTab('search');

async function doSearch(){
  const q = document.getElementById('searchBox').value.trim();
  if(!q) return;
  const raw = await window.pywebview.api.winget_search(q);
  let results = [];
  try{
    results = JSON.parse(raw);
  }catch(e){
    showErrorPopup('Search parse error: '+e.message);
    return;
  }
  renderSearchResults(results);
}

async function loadInstalledPackages(){
  const raw = await window.pywebview.api.winget_list_installed();
  let results = [];
  try{
    results = JSON.parse(raw);
  }catch(e){
    showErrorPopup('Installed packages parse error: '+e.message+'\n'+raw);
    return;
  }
  installedIds = new Set(results.map(r=>r[1]));
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
      <div class="font-bold text-lg mb-2">${pkg[0]}</div>
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

async function doInstall(pkgid){
  await window.pywebview.api.winget_install(pkgid);
}

async function doUninstall(pkgid){
  await window.pywebview.api.winget_uninstall(pkgid);
}

function showErrorPopup(msg){
  errorLog.textContent = msg;
  errorModal.classList.remove('hidden');
}

function closeErrorModal(){
  errorModal.classList.add('hidden');
  errorLog.textContent = '';
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
                    if escaped_line.strip() and not "-" in escaped_line.strip() and not escaped_line.strip() == " " :
                      print(str(escaped_line.strip()))
                      self.window.evaluate_js(f"appendLog({escaped_line})")

                    lower_line = line.lower()
                    is_error_line = any(k in lower_line for k in keywords)
                    if is_error_line:
                        print("error detected")
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
                self.window.evaluate_js(f"updateTask('{task_id}', 'Uninstall Successful', false, true)")
                self.window.evaluate_js(f"appendLog('Task process ended successfully.')")
        except Exception as e:
            self.window.evaluate_js(f"updateTask('{task_id}', 'Exception occurred: {json.dumps(str(e))}', true, false)")
            self.show_error(f"Exception occurred: {str(e)}")

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
