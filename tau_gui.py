import tkinter as tk
from tkinter import ttk, font, filedialog, messagebox
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
    "base": "#323232",
    "surface0": "#0b1a2e",
    "surface1": "#45475a",
    "text": "#cdd6f4",
    "teal": "#ded1c2",
    "blue": "#395d62",
    "sapphire": "#74c7ec",
    "green": "#1c5c54",
    "red": "#f38ba8",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
    "crust": "#11111b",
    "button_active": "#585b70",
    "highlight_line": "#2a2d3d",
    "scrollbar_bg": "#0b1a2e",
    "scrollbar_trough": "#11111b",
    "scrollbar_grip": "#45475a"
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
        self.root.geometry("1400x800")
        self.root.configure(bg=COLORS["base"])

        self.msg_queue = queue.Queue()
        self.process = None
        self.command_start_time = None
        self.last_command = None
        self.tau_executable = find_tau_executable()
        
        # --- Stepper State ---
        self.script_lines = []
        self.current_step_index = 0

        self._setup_styles()
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
        
        # General Styles
        style.configure("TFrame", background=COLORS["base"])
        style.configure("TLabel", background=COLORS["base"], foreground=COLORS["text"])
        
        # Custom Scrollbar Style (Dark Theme)
        style.configure("Vertical.TScrollbar",
            background=COLORS["scrollbar_grip"],
            troughcolor=COLORS["scrollbar_trough"],
            bordercolor=COLORS["base"],
            arrowcolor=COLORS["text"],
            lightcolor=COLORS["scrollbar_grip"],
            darkcolor=COLORS["scrollbar_grip"]
        )
        style.map("Vertical.TScrollbar",
            background=[('active', COLORS["button_active"]), ('pressed', COLORS["sapphire"])]
        )

        # Custom Button Style
        style.configure("Action.TButton", 
            background=COLORS["surface1"], 
            foreground=COLORS["text"],
            borderwidth=1,
            focusthickness=3,
            focuscolor=COLORS["sapphire"]
        )
        style.map("Action.TButton",
            background=[('active', COLORS["button_active"]), ('disabled', COLORS["crust"])],
            foreground=[('disabled', COLORS["surface1"])]
        )
        
        self.mono_font = font.Font(family="Courier New", size=10)
        self.ui_font = font.Font(family="Helvetica", size=10)
        self.tiny_font = font.Font(family="Helvetica", size=8)

    def _create_styled_text_widget(self, parent, height=None):
        """Helper to create a Text widget with a styled dark scrollbar."""
        container = tk.Frame(parent, bg=COLORS["base"])
        
        # Styled Scrollbar
        scrollbar = ttk.Scrollbar(container, orient="vertical", style="Vertical.TScrollbar")
        
        # Text Widget
        text_widget = tk.Text(
            container, 
            bg=COLORS["base"], 
            fg=COLORS["text"],
            insertbackground="white", 
            font=self.mono_font,
            state='disabled',
            height=height if height else 1,
            yscrollcommand=scrollbar.set,
            relief="flat",
            padx=5, pady=5
        )
        
        scrollbar.config(command=text_widget.yview)
        
        scrollbar.pack(side="right", fill="y")
        text_widget.pack(side="left", fill="both", expand=True)
        
        return container, text_widget

    def _build_layout(self):
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Top Bar ---
        top_bar = tk.Frame(main_container, bg=COLORS["base"])
        top_bar.pack(fill=tk.X, pady=(0, 5))
        
        # LEFT: Config & Exit (App Controls)
        self.config_btn = ttk.Button(
            top_bar, text="⚙ Config Tau", style="Action.TButton", command=self.prompt_for_executable
        )
        self.config_btn.pack(side=tk.LEFT)

        self.exit_btn = ttk.Button(
            top_bar, text="Exit", style="Action.TButton", command=self.root.quit
        )
        self.exit_btn.pack(side=tk.LEFT, padx=5)

        # RIGHT: Script Controls (Pack Order: Status <- Step <- Load)
        self.script_status = tk.Label(
            top_bar, text="No script loaded", bg=COLORS["base"], fg=COLORS["surface1"], font=self.ui_font
        )
        self.script_status.pack(side=tk.RIGHT, padx=10)

        self.step_btn = ttk.Button(
            top_bar, text="Step Next ▶", style="Action.TButton", state="disabled", command=self.execute_next_step
        )
        self.step_btn.pack(side=tk.RIGHT, padx=5)

        self.load_btn = ttk.Button(
            top_bar, text="📂 Load Script", style="Action.TButton", command=self.load_script
        )
        self.load_btn.pack(side=tk.RIGHT, padx=5)

        # --- Middle Split View ---
        self.paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, bg=COLORS["base"], sashwidth=4, sashrelief=tk.FLAT)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # COLUMN 1: REPL (Left)
        self.left_frame = tk.Frame(self.paned, bg=COLORS["base"])
        self.paned.add(self.left_frame, minsize=500, width=600, stretch="always")

        tk.Label(self.left_frame, text="REPL Output", bg=COLORS["blue"], fg=COLORS["crust"]).pack(fill=tk.X)
        
        repl_container, self.repl_log = self._create_styled_text_widget(self.left_frame)
        repl_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.repl_log.tag_config("error", foreground=COLORS["red"])
        self.repl_log.tag_config("info", foreground=COLORS["teal"])
        self.repl_log.tag_config("prefix", foreground=COLORS["sapphire"]) 

        self.input_entry = tk.Entry(
            self.left_frame, bg=COLORS["surface1"], fg=COLORS["text"], 
            insertbackground="white", font=self.mono_font
        )
        self.input_entry.pack(fill=tk.X, ipady=5)
        self.input_entry.bind("<Return>", self.on_submit)
        self.input_entry.focus_set()

        # COLUMN 2: Script Viewer (Initially Hidden)
        self.mid_frame = tk.Frame(self.paned, bg=COLORS["base"])
        
        tk.Label(self.mid_frame, text="Script Viewer", bg=COLORS["sapphire"], fg=COLORS["crust"]).pack(fill=tk.X)
        
        script_container, self.script_view = self._create_styled_text_widget(self.mid_frame)
        script_container.pack(fill=tk.BOTH, expand=True)
        self.script_view.config(cursor="arrow")
        self.script_view.tag_config("current_line", background=COLORS["surface1"], foreground="#ffffff")

        # COLUMN 3: History & Debug (Right)
        self.right_frame = tk.Frame(self.paned, bg=COLORS["base"])
        self.paned.add(self.right_frame, minsize=250, width=300, stretch="never")

        right_pane_vert = tk.PanedWindow(self.right_frame, orient=tk.VERTICAL, bg=COLORS["base"], sashwidth=4)
        right_pane_vert.pack(fill=tk.BOTH, expand=True)

        # History
        hist_frame = tk.Frame(right_pane_vert, bg=COLORS["base"])
        right_pane_vert.add(hist_frame, height=200)
        tk.Label(hist_frame, text="History", bg=COLORS["green"], fg=COLORS["crust"]).pack(fill=tk.X)
        
        hist_container, self.history_log = self._create_styled_text_widget(hist_frame)
        hist_container.pack(fill=tk.BOTH, expand=True)

        # Debug
        debug_frame = tk.Frame(right_pane_vert, bg=COLORS["base"])
        right_pane_vert.add(debug_frame, height=200)
        tk.Label(debug_frame, text="Debug Log", bg=COLORS["teal"], fg=COLORS["crust"]).pack(fill=tk.X)
        
        debug_container, self.debug_log = self._create_styled_text_widget(debug_frame)
        debug_container.pack(fill=tk.BOTH, expand=True)
        
        self.debug_log.tag_config("send", foreground=COLORS["pink"])
        self.debug_log.tag_config("recv", foreground=COLORS["mauve"])

        # --- Footer ---
        footer_bar = tk.Frame(main_container, bg=COLORS["base"])
        footer_bar.pack(fill=tk.X, pady=(5, 0), side=tk.BOTTOM)

        self.stats_label = tk.Label(
            footer_bar, text="CPU: 0.0%  RAM: 0.0%", bg=COLORS["base"], fg=COLORS["surface1"], font=self.tiny_font
        )
        self.stats_label.pack(side=tk.RIGHT)

    def load_script(self):
        initial_dir = Path.cwd()
        filename = filedialog.askopenfilename(
            title="Open Tau Script",
            initialdir=initial_dir,
            filetypes=[("Tau Scripts", "*.tau"), ("All Files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.script_lines = [line for line in content.splitlines()]
                self.current_step_index = 0
                
                # Show the Middle Pane if not visible
                if str(self.mid_frame) not in self.paned.panes():
                    self.paned.add(self.mid_frame, after=self.left_frame, minsize=250, width=300, stretch="never")

                self.script_view.config(state='normal')
                self.script_view.delete('1.0', tk.END)
                self.script_view.insert('1.0', content)
                self.script_view.config(state='disabled')
                
                if not any(line.strip() for line in self.script_lines):
                    messagebox.showinfo("Empty File", "The selected file is empty.")
                    return

                self.step_btn.config(state="normal")
                self.script_status.config(text=f"Loaded: {Path(filename).name}", fg=COLORS["sapphire"])
                self.log_to_widget("repl", f"--- Script Loaded: {Path(filename).name} ---", "info")
                self.highlight_current_line()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read file:\n{e}")

    def close_script_viewer(self):
        """Clears content and hides the script viewer pane."""
        self.script_view.config(state='normal')
        self.script_view.delete('1.0', tk.END)
        self.script_view.config(state='disabled')
        
        # Check if the pane is currently being shown before trying to hide it
        if str(self.mid_frame) in self.paned.panes():
            self.paned.forget(self.mid_frame)

    def highlight_current_line(self):
        self.script_view.tag_remove("current_line", "1.0", tk.END)
        if self.current_step_index < len(self.script_lines):
            line_num = self.current_step_index + 1
            start = f"{line_num}.0"
            end = f"{line_num}.end"
            self.script_view.tag_add("current_line", start, end)
            self.script_view.see(start)

    def execute_next_step(self):
        # 1. Skip empty lines
        while self.current_step_index < len(self.script_lines):
            line = self.script_lines[self.current_step_index]
            if line.strip(): break
            self.current_step_index += 1 
        
        # 2. Check if we reached the end
        if self.current_step_index >= len(self.script_lines):
            self._finish_script()
            return

        # 3. Execute the current command
        command = self.script_lines[self.current_step_index]
        self.send_command(command)
        self.current_step_index += 1
        
        # 4. Check if there are any lines left after this one
        temp_index = self.current_step_index
        while temp_index < len(self.script_lines):
            if self.script_lines[temp_index].strip(): break
            temp_index += 1
        
        if temp_index < len(self.script_lines):
             # Update highlighting for the NEXT step
             self.highlight_current_line()
             self.script_status.config(text=f"Step: {self.current_step_index}/{len(self.script_lines)}")
        else:
             # No more lines? Finish now.
             self._finish_script()

    def _finish_script(self):
        self.script_status.config(text="Script finished", fg=COLORS["green"])
        self.step_btn.config(state="disabled")
        self.close_script_viewer() # This hides the screen

    def send_command(self, command):
        if self.process and self.process.poll() is None:
            if command.strip().lower() in ["clear", "cls"]:
                self.repl_log.config(state='normal')
                self.repl_log.delete('1.0', tk.END)
                self.repl_log.config(state='disabled')
                try:
                    self.process.stdin.write("\n")
                    self.process.stdin.flush()
                except Exception: pass
                return

            self.log_to_widget("history", f"» {command}")
            self.log_to_widget("debug", f"[{datetime.now().time()}] ▶ SEND: {command}", "send")
            
            self.command_start_time = time.monotonic()
            self.last_command = command
            
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except Exception as e:
                self.log_to_widget("repl", f"Error writing to process: {e}", "error")
        else:
            self.log_to_widget("repl", "Tau process is not running.", "error")

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
            if widget_name == "repl" and text.startswith("Tau responds: "):
                prefix = "Tau responds:" + "\n"
                content = text[len(prefix):] 
                widget.insert(tk.END, prefix, "prefix")
                widget.insert(tk.END, content + "\n", tag)
            else:
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
                    
                    is_prompt = cleaned_line == prompt_str
                    if is_prompt: continue 

                    is_echo = self.last_command is not None and cleaned_line == self.last_command
                    is_prompt_and_echo = self.last_command is not None and cleaned_line == f"{prompt_str} {self.last_command}"

                    if is_echo or is_prompt_and_echo:
                        if is_echo or is_prompt_and_echo: self.last_command = None
                        is_response_start = True 
                        continue

                    final_output = cleaned_line
                    if is_response_start:
                        final_output = f"Tau responds: {cleaned_line}"
                        is_response_start = False
                    
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
        if command:
            self.send_command(command)
            self.input_entry.delete(0, tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = TauGUI(root)
    root.mainloop()