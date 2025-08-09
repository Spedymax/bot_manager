from flask import Flask, render_template, redirect, url_for
from flask_socketio import SocketIO
import subprocess, os, yaml, psutil, threading, time

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')
BOTS_DIR = "/home/spedymax/bot_manager/bots"

def load_bots():
    bots = {}
    os.makedirs(BOTS_DIR, exist_ok=True)
    for file in os.listdir(BOTS_DIR):
        if file.endswith(".yml"):
            with open(os.path.join(BOTS_DIR, file)) as f:
                bot = yaml.safe_load(f)
                if 'log' not in bot or not bot['log']:
                    bot['log'] = f"/home/spedymax/logs/{bot['name']}.log"
                bots[bot['name']] = bot
    return bots

def is_running(bot):
    for p in psutil.process_iter(['cmdline']):
        cmd = p.info.get('cmdline') or []
        if isinstance(cmd, list):
            cmdline = " ".join(cmd)
        else:
            cmdline = str(cmd)
        if bot['path'] in cmdline:
            return True
    return False

def start_bot(bot):
    os.makedirs(os.path.dirname(bot['log']), exist_ok=True)
    log_fd = open(bot['log'], 'a')
    subprocess.Popen([bot['venv'], bot['path']], stdout=log_fd, stderr=log_fd, close_fds=True)
    socketio.emit("log", {"bot": bot['name'], "message": "Started\n"})

def stop_bot(bot):
    for p in psutil.process_iter(['pid','cmdline']):
        cmd = p.info.get('cmdline') or []
        if isinstance(cmd, list):
            cmdline = " ".join(cmd)
        else:
            cmdline = str(cmd)
        if bot['path'] in cmdline:
            try:
                psutil.Process(p.info['pid']).terminate()
                socketio.emit("log", {"bot": bot['name'], "message": f"Stopped pid {p.info['pid']}\n"})
            except Exception as e:
                socketio.emit("log", {"bot": bot['name'], "message": f"Error stopping {e}\n"})

def restart_bot(bot):
    stop_bot(bot)
    time.sleep(1)
    start_bot(bot)

def update_bot(bot):
    subprocess.run(["git","-C", bot['repo'], "pull", "--rebase"])
    socketio.emit("log", {"bot": bot['name'], "message": "Updated\n"})

@app.route("/")
def index():
    bots = load_bots()
    for b in bots.values():
        b['running'] = is_running(b)
    return render_template("index.html", bots=bots.values())

@app.route("/start/<name>")
def start_route(name):
    bots = load_bots()
    if name in bots:
        start_bot(bots[name])
    return redirect(url_for('index'))

@app.route("/stop/<name>")
def stop_route(name):
    bots = load_bots()
    if name in bots:
        stop_bot(bots[name])
    return redirect(url_for('index'))

@app.route("/restart/<name>")
def restart_route(name):
    bots = load_bots()
    if name in bots:
        restart_bot(bots[name])
    return redirect(url_for('index'))

@app.route("/update/<name>")
def update_route(name):
    bots = load_bots()
    if name in bots:
        update_bot(bots[name])
    return redirect(url_for('index'))

@app.route("/logs/<name>")
def logs_route(name):
    return render_template("logs.html", bot=name)

@socketio.on("subscribe")
def handle_subscribe(data):
    bot_name = data.get('bot')
    bots = load_bots()
    if bot_name not in bots:
        return
    bot = bots[bot_name]
    def tail_log():
        os.makedirs(os.path.dirname(bot['log']), exist_ok=True)
        open(bot['log'], 'a').close()
        try:
            with open(bot['log'], 'r', encoding='utf-8', errors='replace') as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        continue
                    socketio.emit("log", {"bot": bot_name, "message": line})
        except Exception as e:
            socketio.emit("log", {"bot": bot_name, "message": f"Tail error: {e}\n"})
    threading.Thread(target=tail_log, daemon=True).start()

def monitor_loop():
    while True:
        bots = load_bots()
        for bot in bots.values():
            if not is_running(bot):
                socketio.emit("log", {"bot": bot['name'], "message": "Bot not running, attempting start\n"})
                start_bot(bot)
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=8080)
