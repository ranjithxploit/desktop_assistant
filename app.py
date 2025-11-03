import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import subprocess
import os
import shlex
import threading
import json
import time
import psutil
import logging
import pyttsx3
import google.generativeai as genai
import platform


API_KEY = "<gemini_api>"      
MODEL = "gemini-2.0-flash"
LOGFILE = "assistant_actions.log"
MAX_RETRIES = 3
RETRY_DELAY = 2

genai.configure(api_key=API_KEY)


logging.basicConfig(filename=LOGFILE, level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

tts_engine = pyttsx3.init()
def speak(text):
    try:
        tts_engine.say(text)
        tts_engine.runAndWait()
    except Exception:
        pass
def call_llm(prompt):
    for attempt in range(MAX_RETRIES):
        try:
            model = genai.GenerativeModel(MODEL)
            response = model.generate_content(prompt)
            text = response.text if response.text else "[No response from Gemini]"
            return text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "Resource exhausted" in error_msg:
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logging.warning(f"Rate limited. Retrying in {wait_time}s... (Attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error("Max retries reached for rate limiting")
                    return "[LLM error] API rate limit exceeded. Please try again in a moment."
            else:
                logging.exception("LLM call failed")
                return f"[LLM error] {error_msg}"
    
    return "[LLM error] Failed to get response from Gemini API"
def confirm_and_run(action_desc, fn, *args, **kwargs):
    if not messagebox.askyesno("Confirm action", f"Allow this action?\n\n{action_desc}"):
        logging.info(f"User denied action: {action_desc}")
        return "Action cancelled by user."
    logging.info(f"User approved action: {action_desc}")
    try:
        result = fn(*args, **kwargs)
        return result
    except Exception as e:
        logging.exception("Action failed")
        return f"Action error: {e}"

def open_application(path_or_command):
    def _open():
        if os.path.exists(path_or_command):
            os.startfile(path_or_command)
        else:
            subprocess.Popen(shlex.split(path_or_command), shell=True)
    return confirm_and_run(f"Open app/command: {path_or_command}", _open)

def list_top_processes(n=10):
    procs = []
    for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent']):
        try:
            procs.append(p.info)
        except Exception:
            pass
    procs = sorted(procs, key=lambda x: x.get('cpu_percent',0), reverse=True)
    out = "\n".join([f"{i+1}. {p['name']} (pid={p['pid']}) CPU%={p['cpu_percent']} MEM%={round(p['memory_percent'],2)}" for i,p in enumerate(procs[:n])])
    logging.info("Listed processes")
    return out

def run_shell_command(cmd):
    def _run():
        completed = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        return f"Return code: {completed.returncode}\n\nSTDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
    return confirm_and_run(f"Run shell command: {cmd}", _run)

def delete_path(path):
    def _delete():
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
            return f"Directory removed: {path}"
        elif os.path.isfile(path):
            os.remove(path)
            return f"File removed: {path}"
        else:
            return "Path not found."
    return confirm_and_run(f"Delete path: {path}", _delete)

def get_system_info():
    try:
        cpu_count = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot_time = time.ctime(psutil.boot_time())
        
        info = f"""
╔══════════════════════════════════════════╗
║          SYSTEM INFORMATION              ║
╚══════════════════════════════════════════╝
Platform: {platform.system()} {platform.release()}
Machine: {platform.machine()}
Processor: {platform.processor()}
CPU Cores: {cpu_count}
CPU Usage: {cpu_percent}%
RAM Total: {round(memory.total / (1024**3), 2)} GB
RAM Used: {round(memory.used / (1024**3), 2)} GB ({memory.percent}%)
RAM Available: {round(memory.available / (1024**3), 2)} GB
Disk Total: {round(disk.total / (1024**3), 2)} GB
Disk Used: {round(disk.used / (1024**3), 2)} GB ({disk.percent}%)
Disk Free: {round(disk.free / (1024**3), 2)} GB
Boot Time: {boot_time}
        """
        logging.info("System info retrieved")
        return info.strip()
    except Exception as e:
        logging.exception("Failed to get system info")
        return f"Error retrieving system info: {e}"

def get_health_status():
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_percent = psutil.cpu_percent(interval=1)
        
        status = "🟢 HEALTHY"
        alerts = []
        
        if cpu_percent > 80:
            alerts.append(f"⚠️ High CPU usage: {cpu_percent}%")
            status = "🟡 WARNING"
        if memory.percent > 85:
            alerts.append(f"⚠️ High memory usage: {memory.percent}%")
            status = "🟡 WARNING"
        if disk.percent > 90:
            alerts.append(f"⚠️ Low disk space: {disk.percent}% used")
            status = "🔴 CRITICAL"
        
        health_report = f"System Health Status: {status}\n"
        if alerts:
            health_report += "\nAlerts:\n" + "\n".join(alerts)
        else:
            health_report += "All systems operating normally"
        
        logging.info("Health status checked")
        return health_report
    except Exception as e:
        logging.exception("Failed to get health status")
        return f"Error retrieving health status: {e}"
class AssistantApp:
    def __init__(self, root):
        self.root = root
        root.title("AI Desktop Assistant")
        root.geometry("800x600")
        self.chat = scrolledtext.ScrolledText(root, state='disabled', wrap='word', height=22)
        self.chat.pack(fill='both', padx=8, pady=8, expand=True)
        frame = tk.Frame(root)
        frame.pack(fill='x', padx=8, pady=4)
        self.entry = tk.Entry(frame)
        self.entry.pack(side='left', fill='x', expand=True, padx=(0,4))
        self.entry.bind("<Return>", lambda e: self.on_send())

        send_btn = tk.Button(frame, text="Send", command=self.on_send)
        send_btn.pack(side='left')
        actions = tk.Frame(root)
        actions.pack(fill='x', padx=8, pady=(0,8))
        tk.Button(actions, text="Open App", command=self.gui_open_app).pack(side='left')
        tk.Button(actions, text="List Processes", command=self.gui_list_processes).pack(side='left')
        tk.Button(actions, text="Run Command", command=self.gui_run_command).pack(side='left')
        tk.Button(actions, text="Delete Path", command=self.gui_delete_path).pack(side='left')
        tk.Button(actions, text="Sys Info", command=self.gui_system_info).pack(side='left')
        tk.Button(actions, text="Health", command=self.gui_health_status).pack(side='left')
        tk.Button(actions, text="Speak", command=lambda: speak("Assistant online. Ready to help.")).pack(side='right')

        self.log("Assistant started. Type your prompt and press Enter.")

    def log(self, text, role="assistant"):
        self.chat.configure(state='normal')
        self.chat.insert('end', f"{role}: {text}\n\n")
        self.chat.configure(state='disabled')
        self.chat.see('end')

    def on_send(self):
        prompt = self.entry.get().strip()
        if not prompt:
            return
        self.entry.delete(0,'end')
        self.log(prompt, role="you")
        threading.Thread(target=self.handle_prompt, args=(prompt,), daemon=True).start()

    def handle_prompt(self, prompt):
        lower = prompt.lower()
        if lower.startswith("open "):
            target = prompt[5:].strip()
            resp = open_application(target)
            self.log(resp)
            return
        if lower.startswith("list processes") or "processes" in lower:
            resp = list_top_processes()
            self.log(resp)
            return
        if lower.startswith("run ") or lower.startswith("exec "):
            cmd = prompt.split(" ",1)[1]
            resp = run_shell_command(cmd)
            self.log(resp)
            return
        if lower.startswith("delete "):
            path = prompt.split(" ",1)[1]
            resp = delete_path(path)
            self.log(resp)
            return
        if lower.startswith("system info") or lower.startswith("sysinfo"):
            resp = get_system_info()
            self.log(resp)
            return
        if lower.startswith("health") or lower.startswith("status"):
            resp = get_health_status()
            self.log(resp)
            return
        self.log("Thinking...", role="assistant")
        llm_reply = call_llm(prompt)
        logging.info(f"LLM reply: {llm_reply[:200]}")
        self.log(llm_reply)
        try:
            speak(llm_reply)
        except Exception:
            pass

    def gui_open_app(self):
        path = filedialog.askopenfilename(title="Select executable or file")
        if path:
            self.log(f"Opening: {path}")
            resp = open_application(path)
            self.log(resp)

    def gui_list_processes(self):
        self.log("Listing processes...")
        resp = list_top_processes()
        self.log(resp)

    def gui_run_command(self):
        cmd = tk.simpledialog.askstring("Run command", "Enter shell command to run (will prompt for confirmation):")
        if cmd:
            self.log(f"Running: {cmd}")
            resp = run_shell_command(cmd)
            self.log(resp)

    def gui_delete_path(self):
        path = filedialog.askopenfilename(title="Select file to delete")
        if not path:
            path = filedialog.askdirectory(title="Select directory to delete")
        if path:
            self.log(f"Deleting: {path}")
            resp = delete_path(path)
            self.log(resp)

    def gui_system_info(self):
        self.log("Fetching system information...")
        resp = get_system_info()
        self.log(resp)

    def gui_health_status(self):
        self.log("Checking system health...")
        resp = get_health_status()
        self.log(resp)

def main():
    root = tk.Tk()
    app = AssistantApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
