from flask import Flask, render_template, redirect, url_for, jsonify
from flask_socketio import SocketIO
import subprocess, os, yaml, psutil, threading, time
from collections import deque

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')
BOTS_DIR = "/home/spedymax/bot_manager/bots"
LOGS_DIR = "/home/spedymax/logs"
LOG_HISTORY_LINES = 200

# Храним процессы ботов
running_processes = {}

def load_bots():
    bots = {}
    os.makedirs(BOTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    for file in os.listdir(BOTS_DIR):
        if file.endswith(".yml"):
            with open(os.path.join(BOTS_DIR, file)) as f:
                bot = yaml.safe_load(f)
                if 'log' not in bot or not bot['log']:
                    bot['log'] = os.path.join(LOGS_DIR, f"{bot['name']}.log")
                bots[bot['name']] = bot
    return bots

def is_running(bot):
    return bot['name'] in running_processes and running_processes[bot['name']].poll() is None

def kill_existing(bot):
    """Убивает все процессы с этим main.py"""
    for p in psutil.process_iter(['pid', 'cmdline']):
        cmd = p.info.get('cmdline') or []
        if isinstance(cmd, list) and bot['path'] in cmd:
            try:
                psutil.Process(p.info['pid']).terminate()
            except Exception:
                pass

def stream_logs(bot, process):
    """Читает stdout процесса и отправляет в Socket.IO + файл"""
    with open(bot['log'], "a", encoding="utf-8") as log_file:
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            socketio.emit("log", {"bot": bot['name'], "message": line})

def start_bot(bot):
    # Убиваем все старые процессы
    kill_existing(bot)

    os.makedirs(os.path.dirname(bot['log']), exist_ok=True)

    process = subprocess.Popen(
        [bot['venv'], bot['path']],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    running_processes[bot['name']] = process

    threading.Thread(target=stream_logs, args=(bot, process), daemon=True).start()
    socketio.emit("log", {"bot": bot['name'], "message": "Started\n"})

def stop_bot(bot):
    kill_existing(bot)
    if not is_running(bot):
        return
    process = running_processes[bot['name']]
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    socketio.emit("log", {"bot": bot['name'], "message": f"Stopped pid {process.pid}\n"})
    del running_processes[bot['name']]

def restart_bot(bot):
    stop_bot(bot)
    time.sleep(1)
    start_bot(bot)

def update_bot(bot):
    subprocess.run(["git", "-C", bot['repo'], "pull", "--rebase"])
    socketio.emit("log", {"bot": bot['name'], "message": "Updated\n"})

def get_last_log_lines(path, num_lines=200):
    if not os.path.exists(path):
        return ["Нет логов\n"]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=num_lines)) or ["Нет логов\n"]

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

@app.route("/logs_history/<name>")
def logs_history(name):
    bots = load_bots()
    if name not in bots:
        return jsonify(["Нет такого бота\n"])
    lines = get_last_log_lines(bots[name]['log'], LOG_HISTORY_LINES)
    return jsonify(lines)

def monitor_loop():
    while True:
        bots = load_bots()
        for bot in bots.values():
            if not is_running(bot):
                kill_existing(bot)  # убиваем висяки перед рестартом
                socketio.emit("log", {"bot": bot['name'], "message": "Bot not running, attempting start\n"})
                start_bot(bot)
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=8888)
