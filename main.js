const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path'), fs = require('fs'), readline = require('readline');
const { spawn, execFile } = require('child_process');

const PY = process.env.CODECLOSE_PY || (process.platform === 'win32' ? 'python' : 'python3');
const ENGINE = path.join(__dirname, 'engine', 'closer.py');
const outDir = () => path.join(app.getPath('documents'), 'CodeClose', 'salida');
let win = null, child = null, lastExe = null;

function createWindow() {
  win = new BrowserWindow({
    width: 1120, height: 740, minWidth: 820, minHeight: 600,
    frame: false, show: false, backgroundColor: '#14141b', title: 'CodeClose',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false }
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', e => e.preventDefault());
  win.on('closed', () => { killChild(); win = null; });
}

function killChild() {
  if (!child) return;
  if (process.platform === 'win32') execFile('taskkill', ['/pid', String(child.pid), '/T', '/F']);
  else child.kill();
}

function py(args) {
  return spawn(PY, ['-u', ENGINE, ...args], {
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' }
  });
}

ipcMain.on('win', (_, a) => {
  if (!win) return;
  if (a === 'min') win.minimize();
  else if (a === 'max') win.isMaximized() ? win.unmaximize() : win.maximize();
  else win.close();
});

ipcMain.handle('outdir', () => outDir());

ipcMain.handle('pick', async () => {
  const r = await dialog.showOpenDialog(win, { title: 'Selecciona tu proyecto', properties: ['openFile'], filters: [{ name: 'Proyecto ZIP', extensions: ['zip'] }] });
  if (r.canceled || !r.filePaths[0]) return null;
  const p = r.filePaths[0];
  return { name: path.basename(p), size: fs.statSync(p).size, path: p };
});

ipcMain.handle('scan', (_, zip) => new Promise(res => {
  if (typeof zip !== 'string' || !/\.zip$/i.test(zip)) return res(null);
  let out = '';
  const p = py(['scan', zip]);
  p.stdout.on('data', d => out += d);
  p.on('error', () => res(null));
  p.on('close', () => { try { res(JSON.parse(out.trim().split('\n').pop())); } catch { res(null); } });
}));

ipcMain.handle('build', (_, o) => new Promise(res => {
  if (child) return res({ ok: false, error: 'Ya hay una compilacion en curso.' });
  if (!o || typeof o.file !== 'string' || !/\.zip$/i.test(o.file)) return res({ ok: false, error: 'Archivo ZIP no valido.' });
  const engine = ['nuitka', 'pyinstaller'].includes(o.engine) ? o.engine : 'nuitka';
  const args = ['build', o.file, '--entry', String(o.entry), '--name', String(o.out), '--engine', engine, '--outdir', outDir()];
  ['onefile', 'obfuscate', 'noconsole'].forEach(k => o[k] && args.push('--' + k));

  let err = null, errTxt = '';
  lastExe = null;
  child = py(args);
  readline.createInterface({ input: child.stdout }).on('line', l => {
    let m; try { m = JSON.parse(l); } catch { return; }
    if (m.error) err = m.error;
    if (m.done) lastExe = m.exe;
    if (m.msg !== undefined && win) win.webContents.send('progress', { step: m.step, pct: m.pct, msg: m.msg });
  });
  child.stderr.on('data', d => errTxt += d);
  child.on('error', e => { child = null; res({ ok: false, error: 'No se pudo iniciar Python: ' + e.message }); });
  child.on('close', code => {
    child = null;
    if (!err && code === 0 && lastExe) return res({ ok: true, exe: lastExe });
    res({ ok: false, error: err || errTxt.slice(-400) || 'El motor termino con codigo ' + code });
  });
}));

ipcMain.handle('open', () => {
  if (lastExe && fs.existsSync(lastExe)) return shell.showItemInFolder(lastExe);
  fs.mkdirSync(outDir(), { recursive: true });
  shell.openPath(outDir());
});

ipcMain.handle('save', async () => {
  if (!lastExe || !fs.existsSync(lastExe)) return;
  const r = await dialog.showSaveDialog(win, { defaultPath: path.basename(lastExe), filters: [{ name: 'Ejecutable', extensions: ['exe'] }] });
  if (!r.canceled && r.filePath) fs.copyFileSync(lastExe, r.filePath);
});

app.setAppUserModelId('com.xl1f3.codeclose');
app.whenReady().then(() => { Menu.setApplicationMenu(null); createWindow(); });
app.on('window-all-closed', () => app.quit());
