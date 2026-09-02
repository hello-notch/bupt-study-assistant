const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("youxuebanCredentials", {
  load: () => ipcRenderer.invoke("youxueban:credentials:load"),
  save: (value) => ipcRenderer.invoke("youxueban:credentials:save", value),
  clear: () => ipcRenderer.invoke("youxueban:credentials:clear"),
});
