#!/usr/bin/env python3
"""CodeClose engine - by xL1F3 Software

  closer.py scan  <zip>
  closer.py build <zip> --entry main.py --name app --engine nuitka --onefile --obfuscate --noconsole --outdir DIR

Cada evento sale como una linea JSON: {"step","pct","msg"} | {"done","exe",...} | {"error"}
"""
import argparse, collections, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, zipfile

WIN = os.name == "nt"
EXT = ".exe" if WIN else ""
COMMON = ("main.py", "app.py", "run.py", "__main__.py", "gui.py", "start.py")
SKIP = {"__pycache__", "venv", ".venv", "env", "build", "dist", "node_modules"}
PLUGINS = {"tkinter": "tk-inter", "PyQt5": "pyqt5", "PyQt6": "pyqt6", "PySide6": "pyside6", "PySide2": "pyside2"}


class Fail(Exception):
    pass


def emit(**k):
    print(json.dumps(k, ensure_ascii=False), flush=True)


def root_prefix(names):
    """Si el zip trae una unica carpeta raiz, la devuelve (con '/') para entrar en ella."""
    names = [n for n in names if not n.startswith("__MACOSX")]
    tops = {n.split("/")[0] for n in names}
    if len(tops) == 1:
        t = tops.pop()
        if all(n.startswith(t + "/") for n in names):
            return t + "/"
    return ""


def scan(zp):
    found, req = [], False
    with zipfile.ZipFile(zp) as z:
        pre = root_prefix(z.namelist())
        for n in z.namelist():
            if n.startswith("__MACOSX") or n.endswith("/") or not n.startswith(pre):
                continue
            rel = n[len(pre):]
            if rel == "requirements.txt":
                req = True
            if not rel.endswith(".py") or rel.count("/") > 1:
                continue
            if os.path.basename(rel) in COMMON or b"__main__" in z.read(n)[:200000]:
                found.append(rel)
    found.sort(key=lambda r: (COMMON.index(r) if r in COMMON else 99, r))
    print(json.dumps({"entries": found, "requirements": req}), flush=True)


def extract(zp, dest):
    real = os.path.realpath(dest)
    with zipfile.ZipFile(zp) as z:
        for m in z.infolist():  # proteccion zip-slip
            t = os.path.realpath(os.path.join(dest, m.filename))
            if t != real and not t.startswith(real + os.sep):
                raise Fail("El ZIP contiene rutas no seguras: " + m.filename)
        pre = root_prefix(z.namelist())
        z.extractall(dest)
    return os.path.normpath(os.path.join(dest, pre)) if pre else dest


def run(cmd, cwd, step, pct, quiet=False):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", creationflags=0x08000000 if WIN else 0)
    tail, last = collections.deque(maxlen=20), 0.0
    for line in p.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        if not quiet and time.time() - last > 0.5:  # limita el ritmo del registro
            last = time.time()
            emit(step=step, pct=pct, msg=line[:180])
    if p.wait() != 0:
        raise Fail("Fallo en: " + " ".join(cmd[1:5]) + "\n" + "\n".join(tail))


def data_items(proj):
    """Archivos/carpetas de datos (imagenes, json...) que NO son codigo .py"""
    out = []
    for n in sorted(os.listdir(proj)):
        p = os.path.join(proj, n)
        if n in SKIP or n.startswith("."):
            continue
        if os.path.isdir(p):
            if any(not f.endswith((".py", ".pyc")) for _, _, fs in os.walk(p) for f in fs):
                out.append((p, n))
        elif not n.endswith((".py", ".pyc")) and not n.lower().startswith(("readme", "license", "requirements")):
            out.append((p, n))
    return out


def plugins(proj):
    found = set()
    for r, ds, fs in os.walk(proj):
        ds[:] = [d for d in ds if d not in SKIP and not d.startswith(".")]
        for f in fs:
            if f.endswith(".py"):
                with open(os.path.join(r, f), encoding="utf-8", errors="ignore") as h:
                    found |= {PLUGINS[m] for m in re.findall(
                        r"^\s*(?:from|import)\s+(tkinter|PyQt5|PyQt6|PySide6|PySide2)\b", h.read(), re.M)}
    return sorted(found)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(a):
    name = re.sub(r"[^\w\-]", "_", a.name) or "app"
    if not os.path.isfile(a.zip):
        raise Fail("No se encuentra el archivo ZIP.")
    work = tempfile.mkdtemp(prefix="codeclose_")
    try:
        # 0 · Extraer
        emit(step=0, pct=3, msg="Descomprimiendo proyecto…")
        proj = extract(a.zip, os.path.join(work, "src"))
        if not os.path.isfile(os.path.join(proj, a.entry)):
            raise Fail("No existe el punto de entrada: " + a.entry)
        emit(step=0, pct=14, msg="Proyecto extraido · entrada: " + a.entry)

        # 1 · Dependencias (entorno aislado por compilacion)
        emit(step=1, pct=18, msg="Creando entorno aislado…")
        venv = os.path.join(work, "venv")
        run([sys.executable, "-m", "venv", venv], work, 1, 20, True)
        vpy = os.path.join(venv, "Scripts" if WIN else "bin", "python" + EXT)
        tools = ["nuitka", "ordered-set", "zstandard"] if a.engine == "nuitka" else ["pyinstaller"]
        emit(step=1, pct=24, msg="Instalando " + tools[0] + "…")
        pip = [vpy, "-m", "pip", "install", "--disable-pip-version-check", "-q"]
        run(pip + tools, work, 1, 26, True)
        req = os.path.join(proj, "requirements.txt")
        if os.path.isfile(req):
            emit(step=1, pct=30, msg="Instalando requirements.txt…")
            run(pip + ["-r", req], proj, 1, 32, True)

        # 2 · Compilar
        dist = os.path.join(work, "dist")
        os.makedirs(dist)
        data = data_items(proj)
        if a.engine == "nuitka":
            cmd = [vpy, "-m", "nuitka", "--assume-yes-for-downloads", "--remove-output",
                   "--output-dir=" + dist, "--output-filename=" + name + EXT,
                   "--onefile" if a.onefile else "--standalone"]
            if a.noconsole:
                cmd.append("--windows-console-mode=disable")
            if a.obfuscate:
                cmd += ["--python-flag=no_docstrings", "--python-flag=no_asserts"]
            cmd += ["--enable-plugin=" + p for p in plugins(proj)]
            cmd += ["--include-data-%s=%s=%s" % ("dir" if os.path.isdir(p) else "files", p, n) for p, n in data]
            if data:
                cmd.append("--noinclude-data-files=*.py")
            cmd.append(a.entry)
        else:
            cmd = [vpy, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", dist,
                   "--workpath", os.path.join(work, "pi"), "--specpath", work, "--name", name,
                   "--onefile" if a.onefile else "--onedir"]
            if a.noconsole:
                cmd.append("--noconsole")
            for p, n in data:
                cmd += ["--add-data", p + os.pathsep + (n if os.path.isdir(p) else ".")]
            cmd.append(os.path.join(proj, a.entry))
        emit(step=2, pct=36, msg="Compilando con %s… (puede tardar varios minutos)" % a.engine.capitalize())
        run(cmd, proj, 2, 60)

        # 3 · Proteger (limpiar artefactos intermedios + huella SHA-256)
        emit(step=3, pct=86, msg="Protegiendo: limpiando artefactos intermedios…")
        exe = next((os.path.join(r, f) for r, _, fs in os.walk(dist) for f in fs if f == name + EXT), None)
        if not exe:
            raise Fail("No se genero el ejecutable. Revisa el registro.")
        for d in os.listdir(dist):
            if d.endswith((".build", ".onefile-build")):
                shutil.rmtree(os.path.join(dist, d), ignore_errors=True)
        digest = sha256(exe)

        # 4 · Entregar
        emit(step=4, pct=95, msg="Entregando ejecutable…")
        os.makedirs(a.outdir, exist_ok=True)
        if a.onefile:
            final = os.path.join(a.outdir, name + EXT)
            shutil.copy2(exe, final)
        else:
            folder = os.path.join(a.outdir, name)
            shutil.rmtree(folder, ignore_errors=True)
            shutil.copytree(os.path.dirname(exe), folder)
            final = os.path.join(folder, name + EXT)
        with open(final + ".sha256", "w") as f:
            f.write("%s  %s\n" % (digest, os.path.basename(final)))
        emit(done=True, exe=final, sha256=digest, step=4, pct=100, msg="¡Listo! SHA-256: " + digest[:16] + "…")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("scan").add_argument("zip")
    b = sp.add_parser("build")
    b.add_argument("zip")
    b.add_argument("--entry", default="main.py")
    b.add_argument("--name", default="app")
    b.add_argument("--engine", choices=["nuitka", "pyinstaller"], default="nuitka")
    b.add_argument("--outdir", required=True)
    for f in ("onefile", "obfuscate", "noconsole"):
        b.add_argument("--" + f, action="store_true")
    a = ap.parse_args()
    try:
        scan(a.zip) if a.cmd == "scan" else build(a)
    except Exception as e:
        emit(error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
