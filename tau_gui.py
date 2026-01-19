import tkinter as tk
from tkinter import ttk, scrolledtext, font, filedialog
import subprocess
import threading
import queue
import time
import re
import psutil
import argparse
import configparser
from pathlib import Path
from datetime import datetime

# --- Colors ---
COLORS = {
    "base": "#0b1a2e",
    "surface0": "#0b1a2e",
    "surface1": "#45475a",
    "text": "#cdd6f4",
    "teal": "#ded1c2",
    "blue": "#395d62",
    "sapphire": "#74c7ec", # <--- Ensure this color exists
    "green": "#1c5c54",
    "red": "#f38ba8",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
    "crust": "#11111b"
}

CONFIG_FILE = 'config.ini'

def get_tau_path_from_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if 'Paths' in config and 'TauExecutable' in config['Paths']:
        path = config['Paths']['TauExecutable']
        if "#" in path:
            path = path.split("#")[0].strip()
        if path and Path(path).is_file():
            return path
    return None

def save_tau_path_to_config(path):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if 'Paths' not in config:
        config['Paths'] = {}
    config['Paths']['TauExecutable'] = str(path)
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def find_tau_executable():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau-path", help="Path to the tau executable.")
    args, _ = parser.parse_known_args()
    if args.tau_path and Path(args.tau_path).is_file():
        return args.tau_path

    path_from_config = get_tau_path_from_config()
    if path_from_config:
        return path_from_config

    for path in [Path("./tau"), Path("./tau.exe")]:
        if path.is_file():
            return str(path)
    return None

def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B\[[0-9;?]*[a-zA-Z]')
    return ansi_escape.sub('', text)

class TauGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tau Lang GUI")
        self.root.geometry("1000x700")
        self.root.configure(bg=COLORS["base"])

        self.msg_queue = queue.Queue()
        self.process = None
        self.command_start_time = None
        self.last_command = None
        self.tau_executable = find_tau_executable()

        self._setup_styles()
        self._build_menu()
        self._build_layout()
        
        self.update_stats()
        self.check_queue()
        
        if self.tau_executable:
            self.start_tau_thread()
        else:
            self.root.after(100, self.prompt_for_executable)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background=COLORS["base"])
        style.configure("TLabel", background=COLORS["base"], foreground=COLORS["text"])
        
        self.mono_font = font.Font(family="Courier New", size=10)
        self.ui_font = font.Font(family="Helvetica", size=10)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Configure Tau Path...", command=self.prompt_for_executable)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

    def _build_layout(self):
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Stats
        self.stats_label = tk.Label(
            main_container, 
            text="CPU: 0.0%  RAM: 0.0%", 
            bg=COLORS["surface1"], fg=COLORS["text"],
            font=self.ui_font, pady=5
        )
        self.stats_label.pack(fill=tk.X, pady=(0, 10))

        # Split View
        paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, bg=COLORS["base"], sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True)

        # LEFT COLUMN
        left_frame = tk.Frame(paned, bg=COLORS["base"])
        paned.add(left_frame, minsize=400)

        tk.Label(left_frame, text="REPL Output", bg=COLORS["blue"], fg=COLORS["crust"]).pack(fill=tk.X)
        self.repl_log = scrolledtext.ScrolledText(
            left_frame, bg=COLORS["base"], fg=COLORS["text"], 
            insertbackground="white", font=self.mono_font, state='disabled'
        )
        self.repl_log.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # --- TAG CONFIGURATION ---
        self.repl_log.tag_config("error", foreground=COLORS["red"])
        self.repl_log.tag_config("info", foreground=COLORS["teal"])
        # This defines what the "prefix" tag looks like:
        self.repl_log.tag_config("prefix", foreground=COLORS["sapphire"]) 

        self.input_entry = tk.Entry(
            left_frame, bg=COLORS["surface1"], fg=COLORS["text"], 
            insertbackground="white", font=self.mono_font
        )
        self.input_entry.pack(fill=tk.X, ipady=5)
        self.input_entry.bind("<Return>", self.on_submit)
        self.input_entry.focus_set()

        # RIGHT COLUMN
        right_frame = tk.Frame(paned, bg=COLORS["base"])
        paned.add(right_frame, minsize=300)

        tk.Label(right_frame, text="History", bg=COLORS["green"], fg=COLORS["crust"]).pack(fill=tk.X)
        self.history_log = scrolledtext.ScrolledText(
            right_frame, bg=COLORS["base"], fg=COLORS["text"], 
            font=self.mono_font, state='disabled', height=10
        )
        self.history_log.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tk.Label(right_frame, text="Debug Log", bg=COLORS["teal"], fg=COLORS["crust"]).pack(fill=tk.X)
        self.debug_log = scrolledtext.ScrolledText(
            right_frame, bg=COLORS["base"], fg=COLORS["text"], 
            font=self.mono_font, state='disabled', height=10
        )
        self.debug_log.pack(fill=tk.BOTH, expand=True)
        self.debug_log.tag_config("send", foreground=COLORS["pink"])
        self.debug_log.tag_config("recv", foreground=COLORS["mauve"])

    def prompt_for_executable(self):
        initial_dir = Path.cwd()
        filename = filedialog.askopenfilename(
            title="Select Tau Executable",
            initialdir=initial_dir,
            filetypes=[("Executables", "*.exe"), ("All Files", "*.*")]
        )
        if filename:
            self.tau_executable = filename
            save_tau_path_to_config(filename)
            self.log_to_widget("repl", f"Path updated to: {filename}", "info")
            self.restart_process()

    def restart_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process = None
        self.log_to_widget("repl", "-"*30 + "\nRestarting Tau Process...\n" + "-"*30, "info")
        self.start_tau_thread()

    def update_stats(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        self.stats_label.config(text=f"CPU: {cpu:2.1f}%    RAM: {ram:2.1f}%")
        self.root.after(1000, self.update_stats)

    def log_to_widget(self, widget_name, text, tag=None):
        widget_map = {"repl": self.repl_log, "history": self.history_log, "debug": self.debug_log}
        widget = widget_map.get(widget_name)
        if widget:
            widget.config(state='normal')
            
            # --- COLORING LOGIC ---
            # Check if this is a REPL output line that starts with our prefix
            if widget_name == "repl" and text.startswith("Tau responds: "):
                prefix = "Tau responds: "
                # Safe slice even if text is exactly the prefix length
                content = text[len(prefix):] 
                
                # Insert the prefix with the 'prefix' color tag
                widget.insert(tk.END, prefix, "prefix")
                # Insert the actual content with the normal text color (or incoming tag)
                widget.insert(tk.END, content + "\n", tag)
            else:
                # Normal behavior for all other lines
                widget.insert(tk.END, text + "\n", tag)
                
            widget.see(tk.END)
            widget.config(state='disabled')

    def start_tau_thread(self):
        thread = threading.Thread(target=self._run_process, daemon=True)
        thread.start()

    def _run_process(self):
        if not self.tau_executable:
            self.msg_queue.put(("repl", "Error: Tau executable path not set.", "error"))
            return

        try:
            self.process = subprocess.Popen(
                self.tau_executable,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0
            )
            self.msg_queue.put(("repl", "▶ Tau REPL process started...", "info"))
            self.msg_queue.put(("debug", f"[{datetime.now().time()}] ▶ PROCESS STARTED", "info"))

            is_response_start = True

            while True:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None:
                    break
                
                if line:
                    cleaned_line = strip_ansi_codes(line.strip())
                    if not cleaned_line: continue

                    prompt_str = "tau>"
                    
                    # 1. Check for Prompts (Always skip)
                    is_prompt = cleaned_line == prompt_str
                    if is_prompt:
                        continue 

                    # 2. Check for Echoes (Skip, but RESET the response flag)
                    is_echo = self.last_command is not None and cleaned_line == self.last_command
                    is_prompt_and_echo = self.last_command is not None and cleaned_line == f"{prompt_str} {self.last_command}"

                    if is_echo or is_prompt_and_echo:
                        if is_echo or is_prompt_and_echo: 
                            self.last_command = None
                        # Reset flag: The echo marks the command being processed.
                        # The NEXT line is the start of the response.
                        is_response_start = True 
                        continue

                    # 3. Handle Real Output
                    final_output = cleaned_line
                    if is_response_start:
                        final_output = f"Tau responds: \n" + f"{cleaned_line}"

                        is_response_start = False # Disable for subsequent lines in this block
                    
                    duration = 0.0
                    if self.command_start_time:
                        duration = time.monotonic() - self.command_start_time
                        self.command_start_time = None

                    self.msg_queue.put(("repl", final_output, None))
                    self.msg_queue.put(("debug", f"[{datetime.now().time()}] ◀ RECV ({duration:.4f}s): {cleaned_line}", "recv"))

        except Exception as e:
            self.msg_queue.put(("repl", f"Error: {e}", "error"))
        finally:
            self.msg_queue.put(("debug", f"[{datetime.now().time()}] ■ PROCESS FINISHED", "info"))

    def check_queue(self):
        while not self.msg_queue.empty():
            try:
                target, message, tag = self.msg_queue.get_nowait()
                self.log_to_widget(target, message, tag)
            except queue.Empty:
                pass
        self.root.after(100, self.check_queue)

    def on_submit(self, event):
        command = self.input_entry.get()
        
        if self.process and self.process.poll() is None:
            if command.strip().lower() in ["clear", "cls"]:
                self.repl_log.config(state='normal')
                self.repl_log.delete('1.0', tk.END)
                self.repl_log.config(state='disabled')
                self.input_entry.delete(0, tk.END)
                try:
                    self.process.stdin.write("\n")
                    self.process.stdin.flush()
                except Exception as e:
                    self.log_to_widget("repl", f"Error: {e}", "error")
                return

            self.log_to_widget("history", f"» {command}")
            self.log_to_widget("debug", f"[{datetime.now().time()}] ▶ SEND: {command}", "send")
            self.command_start_time = time.monotonic()
            self.last_command = command
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
                self.input_entry.delete(0, tk.END)
            except Exception as e:
                self.log_to_widget("repl", f"Error writing to process: {e}", "error")
        else:
            self.log_to_widget("repl", "Tau process is not running.", "error")

if __name__ == "__main__":
    root = tk.Tk()
    app = TauGUI(root)
    root.mainloop()