import webview
import subprocess
import threading
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


html_code = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Winget GUI with Sticky Sidebar, Tasks & Logs</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .scrollbar-thin::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    .scrollbar-thin::-webkit-scrollbar-thumb {
      background-color: #a0aec0;
      border-radius: 4px;
    }
    /* animated indeterminate progress */
    @keyframes stripes{
      0%{background-position: 1rem 0}
      100%{background-position: 0 0}
    }
    .animated-stripes{
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
  </style>
</head>
<body class="bg-gray-100 min-h-screen flex">
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

    <div id="packagesContent" class="hidden max-w-4xl mx-auto">
      <h2 class="text-xl font-semibold mb-4">Installed Packages</h2>
      <div id="installedGrid" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
    </div>

    <div id="tasksContent" class="hidden max-w-4xl mx-auto">
      <h2 class="text-xl font-semibold mb-4">Tasks</h2>
      <div id="tasksGrid" class="space-y-4"></div>
    </div>
  </div>

  <div id="errorModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center hidden z-50">
    <div class="bg-white rounded-lg shadow-lg max-w-2xl w-full p-6 mx-4">
      <h3 class="text-xl font-semibold mb-4 text-red-600">Error</h3>
      <pre id="errorLog" class="bg-gray-100 p-4 rounded text-xs font-mono max-h-64 overflow-auto whitespace-pre-wrap"></pre>
      <div class="mt-4 flex justify-end">
        <button onclick="closeErrorModal()" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md transition">Close</button>
      </div>
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
      // Filter results: show packages that match, any package from winget search
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
          <button class="mt-auto ${btnClass} text-white py-1 rounded transition"
                  onclick="${onClickFunc}">${btnLabel}</button>
        `;
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
          <button class="mt-auto bg-red-600 hover:bg-red-700 text-white py-1 rounded transition"
                  onclick="doUninstall('${pkg[1]}')">Uninstall</button>
        `;
        container.appendChild(card);
      });
    }

    // Tasks management

    function addTask(id,type,pkgid){
      tasks[id] = {id,type,pkgid,status:'running',message:'',progress:0};
      renderTasks();
    }

    function updateTask(id,message,error=false){
      if(!tasks[id]) return;
      tasks[id].message += message+'\n';
      if(error) tasks[id].status='error';
      renderTasks();
    }

    function completeTask(id){
      if(!tasks[id]) return;
      tasks[id].status='finished';
      tasks[id].progress=100;
      renderTasks();
      refreshPackages();
    }

    function cancelTask(id){
      if(!tasks[id]) return;
      tasks[id].status='cancelled';
      renderTasks();
      refreshPackages();
    }

    function renderTasks(){
      const container = document.getElementById('tasksGrid');
      container.innerHTML = '';
      Object.values(tasks).forEach(task=>{
        const bars = 'overflow-hidden h-2 mb-2 text-xs flex rounded bg-indigo-200';
        const fill = 'shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-indigo-600 transition-all duration-500';
        const errorMsg = task.status==='error' ? '<div class="text-red-600 font-semibold mb-2">Error occurred</div>' : '';
        const cancelDisabled = task.status!=='running' ? 'disabled' : '';
        let width = Math.min(task.progress, 100);

        // Animate indeterminate progress
        let indCls = '';
        if(task.status==='running' && width === 0){
          indCls = ' animated-stripes bg-indigo-500';
        }

        const html = `<div class="p-4 bg-white rounded-lg shadow flex flex-col" id="task-${task.id}">
            <div class="flex justify-between items-center mb-2 text-sm">
              <div><strong>${task.type.toUpperCase()}</strong> ${task.pkgid}</div>
              <button onclick="cancelTask('${task.id}')" ${cancelDisabled} class="bg-red-500 hover:bg-red-700 disabled:opacity-50 text-white px-3 py-1 rounded">Cancel</button>
            </div>
            ${errorMsg}
            <div class="${bars}">
              <div class="${fill}${indCls}" style="width:${width}%"></div>
            </div>
            <pre class="text-xs font-mono whitespace-pre-wrap max-h-32 overflow-auto">${task.message}</pre>
          </div>`;
        container.insertAdjacentHTML('beforeend',html);
      });
    }

    function refreshPackages(){
      if(contents.packages.classList.contains('hidden')){
        return;
      }
      // If packages tab open, reload installed packages and update search buttons
      window.pywebview.api.winget_list_installed().then(raw=>{
        let results = [];
        try{
          results = JSON.parse(raw);
        }catch(e){
          showErrorPopup('Failed refreshing packages: '+ e.message);
          return;
        }
        installedIds = new Set(results.map(r=>r[1]));
        renderInstalledPackages(results);
        // Also update search results if open
        if(!contents.search.classList.contains('hidden')){
          doSearch();
        }
      });
    }

    // Cancel task stub (no backend cancellation implemented)
    function cancelTask(id){
      if(!tasks[id]) return;
      tasks[id].status = 'cancelled';
      renderTasks();
      refreshPackages();
      appendLog(`Cancellation requested for task ${id}`);
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

    def set_window(self, window):
        self.window = window

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
            parsed = clean_and_split_winget_output(lines)
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
            parsed = clean_and_split_winget_output(lines)
            return json.dumps(parsed)
        except Exception as e:
            self.show_error(str(e))
            return json.dumps([{"error": str(e)}])

    def winget_install(self, pkgid):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"type": "install", "pkgid": pkgid, "status": "running", "message": ""}
        self.window.evaluate_js(f"appendLog('Started install task {task_id} for {pkgid}')")
        self.window.evaluate_js(f"addTask('{task_id}', 'install', '{pkgid}')")

        def run_install():
            try:
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
                )
                error_output = []
                for line in iter(proc.stdout.readline, ""):
                    if self.window:
                        escaped_line = json.dumps(line.strip())
                        self.window.evaluate_js(f"appendLog({escaped_line})")
                        self.window.evaluate_js(f"updateTask('{task_id}', {escaped_line}, false)")
                        if "error" in line.lower() or "failed" in line.lower():
                            error_output.append(line.strip())
                proc.stdout.close()
                proc.wait()
                if error_output:
                    error_message = "\\n".join(error_output)
                    self.window.evaluate_js(f"updateTask('{task_id}', 'Error occurred', true)")
                    self.show_error(error_message)
                else:
                    self.window.evaluate_js(f"completeTask('{task_id}')")
                    self.window.evaluate_js(f"appendLog('Install process ended successfully.')")
            except Exception as e:
                self.window.evaluate_js(f"updateTask('{task_id}', 'Error during install: {json.dumps(str(e))}', true)")
                self.show_error(f"Error during install: {str(e)}")

        threading.Thread(target=run_install, daemon=True).start()
        return True

    def winget_uninstall(self, pkgid):
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {"type": "uninstall", "pkgid": pkgid, "status": "running", "message": ""}
        self.window.evaluate_js(f"appendLog('Started uninstall task {task_id} for {pkgid}')")
        self.window.evaluate_js(f"addTask('{task_id}', 'uninstall', '{pkgid}')")

        def run_uninstall():
            try:
                proc = subprocess.Popen(
                    [
                        "winget",
                        "uninstall",
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
                )
                error_output = []
                for line in iter(proc.stdout.readline, ""):
                    if self.window:
                        escaped_line = json.dumps(line.strip())
                        self.window.evaluate_js(f"appendLog({escaped_line})")
                        self.window.evaluate_js(f"updateTask('{task_id}', {escaped_line}, false)")
                        if "error" in line.lower() or "failed" in line.lower():
                            error_output.append(line.strip())
                proc.stdout.close()
                proc.wait()
                if error_output:
                    error_message = "\\n".join(error_output)
                    self.window.evaluate_js(f"updateTask('{task_id}', 'Error occurred', true)")
                    self.show_error(error_message)
                else:
                    self.window.evaluate_js(f"completeTask('{task_id}')")
                    self.window.evaluate_js(f"appendLog('Uninstall process ended successfully.')")
            except Exception as e:
                self.window.evaluate_js(f"updateTask('{task_id}', 'Error during uninstall: {json.dumps(str(e))}', true)")
                self.show_error(f"Error during uninstall: {str(e)}")

        threading.Thread(target=run_uninstall, daemon=True).start()
        return True

    def show_error(self, message):
        if self.window:
            escaped = json.dumps(message)
            self.window.evaluate_js(f"showErrorPopup({escaped})")

if __name__ == "__main__":
    api = Api()
    window = webview.create_window(
        "Winget GUI with Sticky Sidebar, Tasks & Logs",
        html=html_code,
        js_api=api,
        width=1300,
        height=800,
        resizable=True,
    )
    api.set_window(window)
    webview.start(debug=True)
