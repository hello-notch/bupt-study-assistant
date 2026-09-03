const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("youxuebanRuntime", {
  request: (route, init) => ipcRenderer.invoke("youxueban:runtime:request", route, init),
  notify: (title, body) => ipcRenderer.invoke("youxueban:notify", title, body),
});
