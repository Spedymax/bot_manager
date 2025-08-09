from flask import Flask, render_template, redirect, url_for
import subprocess, os, yaml, psutil

app = Flask(__name__)
BOTS_DIR = "./bots"

def get_bots():
    bots = []
    for file in os.listdir(BOTS_DIR):
        if file.endswith(".yml"):
            with open(os.path.join(BOTS_DIR, file)) as f:
                bots.append(yaml.safe_load(f))
    return bots

def is_running(bot):
    for p in psutil.process_iter(['cmdline']):
        if p.info['cmdline'] and bot['path'] in " ".join(p.info['cmdline']):
            return True
    return False

@app.route("/")
def index():
    bots = get_bots()
    for bot in bots:
        bot['running'] = is_running(bot)
    return render_template("index.html", bots=bots)

@app.route("/start/<name>")
def start_bot(name):
    bot = next(b for b in get_bots() if b["name"] == name)
    subprocess.Popen([bot["venv"], bot["path"]])
    return redirect(url_for("index"))

@app.route("/stop/<name>")
def stop_bot(name):
    for p in psutil.process_iter(['pid','cmdline']):
        if p.info['cmdline'] and name in " ".join(p.info['cmdline']):
            psutil.Process(p.info['pid']).terminate()
    return redirect(url_for("index"))

@app.route("/restart/<name>")
def restart_bot(name):
    stop_bot(name)
    start_bot(name)
    return redirect(url_for("index"))

@app.route("/update/<name>")
def update_bot(name):
    bot = next(b for b in get_bots() if b["name"] == name)
    subprocess.run(["git", "-C", bot["repo"], "pull", "--rebase"])
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888)
