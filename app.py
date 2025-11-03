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
from pathlib import Path
import pyperclip
from PIL import ImageGrab
from datetime import datetime


API_KEY = "<gemini_api>"      
MODEL = "gemini-2.0-flash"
LOGFILE = "assistant_actions.log"
MAX_RETRIES = 3
RETRY_DELAY = 2

THEME_CONFIG = {
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#ffffff",
        "chat_bg": "#2d2d2d",
        "chat_fg": "#ffffff",
        "button_bg": "#404040",
        "button_fg": "#ffffff",
        "entry_bg": "#3d3d3d",
        "entry_fg": "#ffffff"
    },
    "light": {
        "bg": "#f0f0f0",
        "fg": "#000000",
        "chat_bg": "#ffffff",
        "chat_fg": "#000000",
        "button_bg": "#e0e0e0",
        "button_fg": "#000000",
        "entry_bg": "#ffffff",
        "entry_fg": "#000000"
    }
}

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

def search_files(filename, search_path=None, max_results=20):
    try:
        if search_path is None:
            search_path = os.path.expanduser("~")
        
        results = []
        search_path = Path(search_path)
        
        for path in search_path.rglob(f"*{filename}*"):
            if len(results) >= max_results:
                break
            try:
                if path.is_file():
                    size = path.stat().st_size / (1024**2)
                    results.append(f"{path} ({size:.2f} MB)")
                elif path.is_dir():
                    results.append(f"{path}/ [FOLDER]")
            except (PermissionError, OSError):
                pass
        
        if results:
            search_result = f"Found {len(results)} matches for '{filename}':\n\n" + "\n".join(results)
        else:
            search_result = f"No files found matching '{filename}'"
        
        logging.info(f"File search completed for: {filename}")
        return search_result
    except Exception as e:
        logging.exception("File search failed")
        return f"Search error: {e}"

def get_clipboard():
    try:
        text = pyperclip.paste()
        if text:
            result = f"Clipboard content:\n{text[:500]}"
            if len(text) > 500:
                result += f"\n...(truncated, total {len(text)} chars)"
        else:
            result = "Clipboard is empty"
        logging.info("Clipboard read")
        return result
    except Exception as e:
        logging.exception("Failed to read clipboard")
        return f"Clipboard error: {e}"

def set_clipboard(text):
    try:
        pyperclip.copy(text)
        logging.info(f"Copied to clipboard: {text[:100]}")
        return f"Copied to clipboard: {text[:100]}"
    except Exception as e:
        logging.exception("Failed to set clipboard")
        return f"Clipboard error: {e}"

def clear_clipboard():
    try:
        pyperclip.copy("")
        logging.info("Clipboard cleared")
        return "Clipboard cleared"
    except Exception as e:
        logging.exception("Failed to clear clipboard")
        return f"Clipboard error: {e}"

def take_screenshot(save_path=None):
    try:
        if save_path is None:
            screenshot_dir = os.path.join(os.path.expanduser("~"), "Screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(screenshot_dir, f"screenshot_{timestamp}.png")
        
        screenshot = ImageGrab.grab()
        screenshot.save(save_path)
        logging.info(f"Screenshot saved: {save_path}")
        return f"Screenshot saved: {save_path}"
    except Exception as e:
        logging.exception("Screenshot failed")
        return f"Screenshot error: {e}"

def take_screenshot_region():
    try:
        screenshot_dir = os.path.join(os.path.expanduser("~"), "Screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(screenshot_dir, f"screenshot_region_{timestamp}.png")
        
        screenshot = ImageGrab.grab(bbox=(0, 0, 1024, 768))
        screenshot.save(save_path)
        logging.info(f"Region screenshot saved: {save_path}")
        return f"Region screenshot saved: {save_path}"
    except Exception as e:
        logging.exception("Region screenshot failed")
        return f"Screenshot error: {e}"

def toggle_theme(app_instance, current_theme):
    new_theme = "light" if current_theme == "dark" else "dark"
    app_instance.apply_theme(new_theme)
    return f"Theme switched to {new_theme}"

def save_chat_history(chat_content, filename=None):
    try:
        history_dir = os.path.join(os.path.expanduser("~"), "ChatHistory")
        os.makedirs(history_dir, exist_ok=True)
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chat_history_{timestamp}.txt"
        
        filepath = os.path.join(history_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(chat_content)
        logging.info(f"Chat history saved: {filepath}")
        return f"Chat history saved: {filepath}"
    except Exception as e:
        logging.exception("Failed to save chat history")
        return f"Error saving chat history: {e}"

def load_chat_history(filename):
    try:
        history_dir = os.path.join(os.path.expanduser("~"), "ChatHistory")
        filepath = os.path.join(history_dir, filename)
        
        if not os.path.exists(filepath):
            return f"File not found: {filepath}"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logging.info(f"Chat history loaded: {filepath}")
        return content
    except Exception as e:
        logging.exception("Failed to load chat history")
        return f"Error loading chat history: {e}"

def list_chat_histories():
    try:
        history_dir = os.path.join(os.path.expanduser("~"), "ChatHistory")
        if not os.path.exists(history_dir):
            return "No chat history found"
        
        files = os.listdir(history_dir)
        if not files:
            return "No chat history files"
        
        history_list = "\n".join([f"{i+1}. {f}" for i, f in enumerate(sorted(files)[:20])])
        logging.info("Chat histories listed")
        return f"Available chat histories:\n{history_list}"
    except Exception as e:
        logging.exception("Failed to list chat histories")
        return f"Error listing chat histories: {e}"

class AssistantApp:
    def __init__(self, root):
        self.root = root
        self.current_theme = "dark"
        self.chat_history = []
        root.title("AI Desktop Assistant")
        root.geometry("900x650")
        
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
        tk.Button(actions, text="Search Files", command=self.gui_search_files).pack(side='left')
        tk.Button(actions, text="Clipboard", command=self.gui_get_clipboard).pack(side='left')
        tk.Button(actions, text="Copy", command=self.gui_copy_clipboard).pack(side='left')
        tk.Button(actions, text="Clear Clip", command=self.gui_clear_clipboard).pack(side='left')
        tk.Button(actions, text="Screenshot", command=self.gui_screenshot).pack(side='left')
        tk.Button(actions, text="🌓 Theme", command=self.toggle_app_theme).pack(side='left')
        tk.Button(actions, text="Save Chat", command=self.gui_save_chat).pack(side='left')
        tk.Button(actions, text="Load Chat", command=self.gui_load_chat).pack(side='left')
        tk.Button(actions, text="Chat List", command=self.gui_list_chats).pack(side='left')
        tk.Button(actions, text="Speak", command=lambda: speak("Assistant online. Ready to help.")).pack(side='right')

        self.apply_theme("dark")
        self.log("Assistant started. Type your prompt and press Enter.")

    def log(self, text, role="assistant"):
        self.chat.configure(state='normal')
        self.chat.insert('end', f"{role}: {text}\n\n")
        self.chat.configure(state='disabled')
        self.chat.see('end')
        self.chat_history.append(f"{role}: {text}")

    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        theme = THEME_CONFIG[theme_name]
        
        self.root.configure(bg=theme["bg"])
        self.chat.configure(bg=theme["chat_bg"], fg=theme["chat_fg"], insertbackground=theme["chat_fg"])
        self.entry.configure(bg=theme["entry_bg"], fg=theme["entry_fg"], insertbackground=theme["entry_fg"])
        
        for widget in self.root.winfo_children():
            self.apply_theme_recursive(widget, theme)
        
        logging.info(f"Theme changed to: {theme_name}")

    def apply_theme_recursive(self, widget, theme):
        if isinstance(widget, tk.Button):
            widget.configure(bg=theme["button_bg"], fg=theme["button_fg"], activebackground=theme["button_bg"])
        elif isinstance(widget, tk.Frame):
            widget.configure(bg=theme["bg"])
            for child in widget.winfo_children():
                self.apply_theme_recursive(child, theme)
        elif isinstance(widget, tk.Label):
            widget.configure(bg=theme["bg"], fg=theme["fg"])

    def toggle_app_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme(new_theme)
        self.log(f"Theme switched to {new_theme.upper()}")

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
        if lower.startswith("search ") or lower.startswith("find "):
            query = prompt.split(" ", 1)[1].strip()
            self.log(f"Searching for files matching: {query}...")
            resp = search_files(query)
            self.log(resp)
            return
        if lower.startswith("clipboard") or lower.startswith("get clip"):
            resp = get_clipboard()
            self.log(resp)
            return
        if lower.startswith("copy "):
            text = prompt[5:].strip()
            resp = set_clipboard(text)
            self.log(resp)
            return
        if lower.startswith("clear clip"):
            resp = clear_clipboard()
            self.log(resp)
            return
        if lower.startswith("screenshot") or lower.startswith("screen shot") or lower.startswith("snap"):
            resp = take_screenshot()
            self.log(resp)
            return
        if lower.startswith("screenshot region") or lower.startswith("screenshot area"):
            resp = take_screenshot_region()
            self.log(resp)
            return
        if lower.startswith("theme") or lower.startswith("toggle theme") or lower.startswith("dark") or lower.startswith("light"):
            self.toggle_app_theme()
            return
        if lower.startswith("save chat") or lower.startswith("save history"):
            content = "\n".join(self.chat_history)
            resp = save_chat_history(content)
            self.log(resp)
            return
        if lower.startswith("load chat") or lower.startswith("load history"):
            filename = prompt.split(" ", 2)[2].strip() if len(prompt.split(" ")) > 2 else None
            if filename:
                content = load_chat_history(filename)
                self.log(content)
            else:
                self.log("Please specify filename: load chat [filename]")
            return
        if lower.startswith("chat list") or lower.startswith("list chats"):
            resp = list_chat_histories()
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

    def gui_search_files(self):
        filename = tk.simpledialog.askstring("Search Files", "Enter filename or pattern to search:")
        if filename:
            self.log(f"Searching for: {filename}...")
            resp = search_files(filename)
            self.log(resp)

    def gui_get_clipboard(self):
        self.log("Reading clipboard...")
        resp = get_clipboard()
        self.log(resp)

    def gui_copy_clipboard(self):
        text = tk.simpledialog.askstring("Copy to Clipboard", "Enter text to copy:")
        if text:
            resp = set_clipboard(text)
            self.log(resp)

    def gui_clear_clipboard(self):
        if messagebox.askyesno("Clear Clipboard", "Clear clipboard content?"):
            resp = clear_clipboard()
            self.log(resp)

    def gui_screenshot(self):
        choice = messagebox.askyesnocancel("Screenshot", "Capture full screen?\n\nYes = Full Screen\nNo = Region")
        if choice is True:
            resp = take_screenshot()
            self.log(resp)
        elif choice is False:
            resp = take_screenshot_region()
            self.log(resp)

    def gui_save_chat(self):
        content = "\n".join(self.chat_history)
        resp = save_chat_history(content)
        self.log(resp)

    def gui_load_chat(self):
        filename = tk.simpledialog.askstring("Load Chat", "Enter filename to load:")
        if filename:
            content = load_chat_history(filename)
            self.log(content)

    def gui_list_chats(self):
        self.log("Loading chat history list...")
        resp = list_chat_histories()
        self.log(resp)

def main():
    root = tk.Tk()
    app = AssistantApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
