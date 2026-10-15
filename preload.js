const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  winControl: a => ipcRenderer.send('win', a),
  pickZip: () => ipcRenderer.invoke('pick'),
  getPathForFile: f => webUtils.getPathForFile(f),
  scanZip: p => ipcRenderer.invoke('scan', p),
  startBuild: o => ipcRenderer.invoke('build', o),
  onProgress: cb => {
    ipcRenderer.removeAllListeners('progress');
    ipcRenderer.on('progress', (_, d) => cb(d.step, d.pct, d.msg));
  },
  openFolder: () => ipcRenderer.invoke('open'),
  saveAs: () => ipcRenderer.invoke('save'),
  outDir: () => ipcRenderer.invoke('outdir')
});
