from flask import Flask, render_template, redirect, url_for
from flask_socketio import SocketIO
import subprocess, os, yaml, psutil, threading, time

app = Flask(__name__)
socketio = SocketIO(app)
BOTS_DIR = "./bots"
bots_cache = {}

def load_bots():
    bots = {}
    for file in os.listdir(BOTS_DIR):
        if file.endswith(".yml"):
            with open(os.path.join(BOTS_DIR, file)) as f:
                bot = yaml.safe_load(f)
                bots[bot['name']] = bot
    return bots

def is_running(bot):
    for p in psutil.process_iter(['cmdline']):
        if p.info['cmdline'] and bot['path'] in " ".join(p.info['cmdline']):
            return True
    return False

def start_bot(bot):
    log_file = open(bot["log"], "a")
    subprocess.Popen([bot["venv"], bot["path"]], stdout=log_file, stderr=log_file)
    socketio.emit("log", {"bot": bot["name"], "message": f"Started {bot['name']}"})

def stop_bot(bot):
    for p in psutil.process_iter(['pid', 'cmdline']):
        if p.info['cmdline'] and bot['path'] in " ".join(p.info['cmdline']):
            psutil.Process(p.info['pid']).terminate()
            socketio.emit("log", {"bot": bot["name"], "message": f"Stopped {bot['name']}"})

def restart_bot(bot):
    stop_bot(bot)
    time.sleep(1)
    start_bot(bot)

def update_bot(bot):
    subprocess.run(["git", "-C", bot["repo"], "pull", "--rebase"])
    socketio.emit("log", {"bot": bot["name"], "message": f"Updated {bot['name']}"})

@app.route("/")
def index():
    bots = load_bots()
    for b in bots.values():
        b["running"] = is_running(b)
    return render_template("index.html", bots=bots.values())

@app.route("/start/<name>")
def start_route(name):
    start_bot(load_bots()[name])
    return redirect(url_for("index"))

@app.route("/stop/<name>")
def stop_route(name):
    stop_bot(load_bots()[name])
    return redirect(url_for("index"))

@app.route("/restart/<name>")
def restart_route(name):
    restart_bot(load_bots()[name])
    return redirect(url_for("index"))

@app.route("/update/<name>")
def update_route(name):
    update_bot(load_bots()[name])
    return redirect(url_for("index"))

@app.route("/logs/<name>")
def logs_route(name):
    return render_template("logs.html", bot=name)

@socketio.on("subscribe")
def handle_subscribe(data):
    bot_name = data["bot"]
    bot = load_bots()[bot_name]
    def tail_log():
        with open(bot["log"]) as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                socketio.emit("log", {"bot": bot_name, "message": line})
    threading.Thread(target=tail_log, daemon=True).start()

def monitor_loop():
    while True:
        bots = load_bots()
        for bot in bots.values():
            if not is_running(bot):
                socketio.emit("log", {"bot": bot["name"], "message": "Bot crashed, restarting..."})
                start_bot(bot)
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=8888)
