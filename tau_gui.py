import tkinter as tk
from tkinter import ttk, font, filedialog, messagebox, colorchooser
import subprocess
import threading
import queue
import time
import re
import psutil
import argparse
import configparser
import webbrowser  # NEW: For documentation link
from pathlib import Path
from datetime import datetime

# --- Default Theme (Semantic Names) ---
DEFAULT_THEME = {
    "bg_base": "#3E3D32",
    "bg_surface0": "#3E3D32",
    "bg_surface1": "#3E3D32",
    "fg_text": "#F8EFBA",
    "primary": "#BDC581",       # Used for Prompt/Header/Focus
    "secondary": "#66d9ef",     # Used for extra accents
    "repl_header": "#EAB543",
    "history_header": "#CAD3C8",
    "debug_header": "#FEA47F",
    "error": "#FD7272",
    "success": "#a6e22e",
    "info": "#94BEC7",
    "comment": "#75715E",
    "debug_send": "#FD7272",
    "debug_recv": "#D6A2E8",
    "header_text": "#17170E",
    "button_active": "#75715E",
    "scrollbar_bg": "#272822",
    "scrollbar_trough": "#17170E",
    "scrollbar_grip": "#75715E"
}

CONFIG_FILE = 'config.ini'

# --- ToolTip Helper ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

# --- Config Helpers ---
def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def get_tau_path():
    config = load_config()
    if 'Paths' in config and 'TauExecutable' in config['Paths']:
        path = config['Paths']['TauExecutable']
        if "#" in path: path = path.split("#")[0].strip()
        if path and Path(path).is_file():
            return path
    return None

def save_tau_path(path):
    config = load_config()
    if 'Paths' not in config: config['Paths'] = {}
    config['Paths']['TauExecutable'] = str(path)
    save_config(config)

def load_theme():
    config = load_config()
    theme = DEFAULT_THEME.copy()
    if 'Theme' in config:
        for key in theme:
            if key in config['Theme']:
                theme[key] = config['Theme'][key]
    return theme

def save_theme(colors):
    config = load_config()
    if 'Theme' not in config: config['Theme'] = {}
    for key, value in colors.items():
        config['Theme'][key] = value
    save_config(config)

def find_tau_executable():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau-path", help="Path to the tau executable.")
    args, _ = parser.parse_known_args()
    if args.tau_path and Path(args.tau_path).is_file():
        return args.tau_path
    path = get_tau_path()
    if path: return path
    for p in [Path("./tau"), Path("./tau.exe")]:
        if p.is_file(): return str(p)
    return None

def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B\[[0-9;?]*[a-zA-Z]')
    return ansi_escape.sub('', text)

class TauGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HippieCycling´s Tau-Lang GUI")
        self.root.geometry("1000x700")
        
        self.colors = load_theme()
        self.root.configure(bg=self.colors["bg_base"])

        self.msg_queue = queue.Queue()
        self.process = None
        self.command_start_time = None
        self.last_command = None
        self.tau_executable = find_tau_executable()
        
        # --- State ---
        self.script_lines = []
        self.current_step_index = 0
        self.debug_events = [] 
        self.show_detailed_debug = tk.BooleanVar(value=False)
        self.script_viewer_visible = False
        
        # --- UI Tracking ---
        self.text_widgets = []
        self.frames = []
        self.labels = [] 

        self._setup_styles()
        self._build_layout()
        self.apply_theme()
        
        self.update_stats()
        self.check_queue()
        
        if self.tau_executable:
            self.start_tau_thread()
        else:
            self.root.after(100, self.prompt_for_executable)

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.mono_font = font.Font(family="Courier New", size=10)
        self.ui_font = font.Font(family="Helvetica", size=10)
        self.tiny_font = font.Font(family="Helvetica", size=8)
        self.debug_font = font.Font(family="Courier New", size=8)

    def _update_ttk_styles(self):
        c = self.colors
        self.style.configure("TFrame", background=c["bg_base"])
        self.style.configure("TLabel", background=c["bg_base"], foreground=c["fg_text"])
        self.style.configure("TCheckbutton", background=c["debug_header"], foreground=c["header_text"])
        
        self.style.configure("Vertical.TScrollbar",
            background=c["scrollbar_grip"], troughcolor=c["scrollbar_trough"],
            bordercolor=c["bg_base"], arrowcolor=c["fg_text"],
            lightcolor=c["scrollbar_grip"], darkcolor=c["scrollbar_grip"]
        )
        self.style.map("Vertical.TScrollbar", background=[('active', c["button_active"]), ('pressed', c["primary"])])

        # Base Button Style Configuration
        common_btn_config = {
            "background": c["bg_surface1"], 
            "foreground": c["fg_text"],
            "borderwidth": 1, 
            "focusthickness": 3, 
            "focuscolor": c["primary"]
        }
        
        common_btn_map = {
            "background": [('active', c["button_active"]), ('pressed', c["primary"]), ('disabled', c["bg_surface1"])],
            "foreground": [('disabled', "#888888")]
        }

        # Action Button (Top Bar)
        self.style.configure("Action.TButton", **common_btn_config)
        self.style.map("Action.TButton", **common_btn_map)
        
        # Header Button (Clear History) - Inherits colors, smaller font
        self.style.configure("Header.TButton", font=("Helvetica", 7), padding=1, **common_btn_config)
        self.style.map("Header.TButton", **common_btn_map)
        
        # Icon Button (Send/Defs) - Inherits colors, symbol font
        self.style.configure("Icon.TButton", font=("Segoe UI Symbol", 10), padding=2, width=3, **common_btn_config)
        self.style.map("Icon.TButton", **common_btn_map)

    def apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg_base"])
        self._update_ttk_styles()

        for widget in self.text_widgets:
            widget.configure(bg=c["bg_base"], fg=c["fg_text"], insertbackground=c["fg_text"])
            widget.tag_config("error", foreground=c["error"])
            widget.tag_config("info", foreground=c["info"])
            widget.tag_config("prefix", foreground=c["primary"]) 
            widget.tag_config("send", foreground=c["debug_send"])
            widget.tag_config("recv", foreground=c["debug_recv"])
            widget.tag_config("comment", foreground=c["comment"])
            
            if widget == self.script_view:
                 widget.tag_config("current_line", background=c["bg_surface1"], foreground="#ffffff")

        self.input_entry.configure(bg=c["bg_surface1"], fg=c["fg_text"], insertbackground=c["fg_text"])
        for frame in self.frames: frame.configure(bg=c["bg_base"])
        
        for label, color_key in self.labels:
            bg_color = c[color_key] if color_key in c else c["bg_base"]
            fg_color = c["header_text"] if color_key in ["repl_header", "primary", "history_header", "debug_header"] else c["fg_text"]
            label.configure(bg=bg_color, fg=fg_color)
        
        self.paned.configure(bg=c["bg_base"])
        self.right_pane_vert.configure(bg=c["bg_base"])

    # --- UI Building ---
    def _create_styled_text_widget(self, parent, height=None, custom_font=None):
        container = tk.Frame(parent, bg=self.colors["bg_base"])
        self.frames.append(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", style="Vertical.TScrollbar")
        
        f = custom_font if custom_font else self.mono_font
        
        text_widget = tk.Text(
            container, bg=self.colors["bg_base"], fg=self.colors["fg_text"],
            insertbackground="white", font=f, state='disabled',
            height=height if height else 1, yscrollcommand=scrollbar.set,
            relief="flat", padx=5, pady=5
        )
        self.text_widgets.append(text_widget)
        scrollbar.config(command=text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        text_widget.pack(side="left", fill="both", expand=True)
        return container, text_widget

    def _build_layout(self):
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Top Bar ---
        top_bar = tk.Frame(main_container, bg=self.colors["bg_base"])
        self.frames.append(top_bar)
        top_bar.pack(fill=tk.X, pady=(0, 5))
        
        # Left Group: Exit, Theme, Config, Restart, Docs
        ttk.Button(top_bar, text="Exit", style="Action.TButton", command=self.root.quit).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(top_bar, text="🎨 Theme", style="Action.TButton", command=self.open_theme_editor).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="⚙ Config", style="Action.TButton", command=self.prompt_for_executable).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="⟳ Restart", style="Action.TButton", command=self.restart_process).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="📖 Docs", style="Action.TButton", command=self.open_docs).pack(side=tk.LEFT, padx=5)

        self.script_status = tk.Label(top_bar, text="No script loaded", font=self.ui_font)
        self.labels.append((self.script_status, "bg_base"))
        self.script_status.pack(side=tk.RIGHT, padx=10)

        self.step_btn = ttk.Button(top_bar, text="Step Next ▶", style="Action.TButton", state="disabled", command=self.execute_next_step)
        self.step_btn.pack(side=tk.RIGHT, padx=5)
        
        self.toggle_script_btn = ttk.Button(top_bar, text="👁 Toggle Script", style="Action.TButton", state="disabled", command=self.toggle_script_viewer)
        self.toggle_script_btn.pack(side=tk.RIGHT, padx=5)

        self.load_btn = ttk.Button(top_bar, text="📂 Load .tau File", style="Action.TButton", command=self.load_script)
        self.load_btn.pack(side=tk.RIGHT, padx=5)

        # --- Middle Split ---
        self.paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, bg=self.colors["bg_base"], sashwidth=4, sashrelief=tk.FLAT)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # COL 1: REPL
        self.left_frame = tk.Frame(self.paned)
        self.frames.append(self.left_frame)
        self.paned.add(self.left_frame, minsize=500, width=600, stretch="always")

        lbl_repl = tk.Label(self.left_frame, text="REPL Output")
        lbl_repl.pack(fill=tk.X)
        self.labels.append((lbl_repl, "repl_header"))

        repl_container, self.repl_log = self._create_styled_text_widget(self.left_frame)
        repl_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Command Input Bar
        input_container = tk.Frame(self.left_frame, bg=self.colors["bg_base"])
        self.frames.append(input_container)
        input_container.pack(fill=tk.X)

        self.input_entry = tk.Entry(input_container, font=self.mono_font)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.input_entry.bind("<Return>", self.on_submit)

        # Defs Button (Uses Icon.TButton which now has colors)
        btn_defs = ttk.Button(input_container, text="ƒ", style="Icon.TButton", command=lambda: self.send_command("defs"))
        btn_defs.pack(side=tk.RIGHT, padx=(2, 0), ipady=1)
        ToolTip(btn_defs, "Show definitions")

        # Send Button (Uses Icon.TButton which now has colors)
        btn_send = ttk.Button(input_container, text="➤", style="Icon.TButton", command=lambda: self.on_submit(None))
        btn_send.pack(side=tk.RIGHT, padx=(5, 0), ipady=1)
        ToolTip(btn_send, "Send command")

        # COL 2: Script (Hidden by default)
        self.mid_frame = tk.Frame(self.paned)
        self.frames.append(self.mid_frame)
        lbl_script = tk.Label(self.mid_frame, text=".tau File Viewer")
        lbl_script.pack(fill=tk.X)
        self.labels.append((lbl_script, "primary"))
        script_container, self.script_view = self._create_styled_text_widget(self.mid_frame)
        script_container.pack(fill=tk.BOTH, expand=True)

        # COL 3: Right Panel
        self.right_frame = tk.Frame(self.paned)
        self.frames.append(self.right_frame)
        self.paned.add(self.right_frame, minsize=250, width=300, stretch="never")

        self.right_pane_vert = tk.PanedWindow(self.right_frame, orient=tk.VERTICAL, bg=self.colors["bg_base"], sashwidth=4)
        self.right_pane_vert.pack(fill=tk.BOTH, expand=True)

        # History
        hist_frame = tk.Frame(self.right_pane_vert)
        self.frames.append(hist_frame)
        self.right_pane_vert.add(hist_frame, height=200)
        
        hist_header = tk.Frame(hist_frame)
        hist_header.pack(fill=tk.X)
        lbl_hist = tk.Label(hist_header, text="History")
        lbl_hist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.labels.append((lbl_hist, "history_header"))
        
        # Clear Button (Uses Header.TButton which now has colors)
        ttk.Button(hist_header, text="Clear", style="Header.TButton", width=6, command=self.clear_history).pack(side=tk.RIGHT, padx=2)

        hist_container, self.history_log = self._create_styled_text_widget(hist_frame)
        hist_container.pack(fill=tk.BOTH, expand=True)

        # Debug
        debug_frame = tk.Frame(self.right_pane_vert)
        self.frames.append(debug_frame)
        self.right_pane_vert.add(debug_frame, height=200)
        
        debug_header = tk.Frame(debug_frame)
        debug_header.pack(fill=tk.X)
        lbl_debug = tk.Label(debug_header, text="Debug Log")
        lbl_debug.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.labels.append((lbl_debug, "debug_header"))
        
        ttk.Checkbutton(debug_header, text="+Details", variable=self.show_detailed_debug, 
                        style="TCheckbutton", command=self.refresh_debug_log).pack(side=tk.RIGHT, padx=5)

        debug_container, self.debug_log = self._create_styled_text_widget(debug_frame, custom_font=self.debug_font)
        debug_container.pack(fill=tk.BOTH, expand=True)

        # Footer
        footer_bar = tk.Frame(main_container)
        self.frames.append(footer_bar)
        footer_bar.pack(fill=tk.X, pady=(5, 0), side=tk.BOTTOM)
        self.stats_label = tk.Label(footer_bar, text="CPU: 0.0%  RAM: 0.0%", font=self.tiny_font)
        self.stats_label.pack(side=tk.RIGHT)
        self.labels.append((self.stats_label, "bg_surface1"))

    # --- Feature Logic ---
    def open_docs(self):
        webbrowser.open("https://github.com/IDNI/tau-lang")

    def clear_history(self):
        self.history_log.config(state='normal')
        self.history_log.delete('1.0', tk.END)
        self.history_log.config(state='disabled')

    def refresh_debug_log(self):
        self.debug_log.config(state='normal')
        self.debug_log.delete('1.0', tk.END)
        for event in self.debug_events: self._append_debug_entry(event)
        self.debug_log.see(tk.END)
        self.debug_log.config(state='disabled')

    def _append_debug_entry(self, event):
        timestamp = event['time']
        dtype = event['type']
        text = event['text']
        duration = event.get('duration', 0.0)
        is_detailed = self.show_detailed_debug.get()
        display_text, tag = "", ""
        
        if dtype == "send":
            tag = "send"
            display_text = f"[{timestamp}] ▶ SEND: {text}\n" if is_detailed else f"[{timestamp}] ▶ Command Executed\n"
        elif dtype == "recv":
            tag = "recv"
            display_text = f"[{timestamp}] ◀ RECV ({duration:.4f}s): {text}\n" if is_detailed else f"[{timestamp}] ◀ REPL Responded ({duration:.4f}s)\n"
        elif dtype == "info":
            tag = "info"
            display_text = f"[{timestamp}] ■ {text}\n"

        self.debug_log.insert(tk.END, display_text, tag)

    # --- Script Viewer Logic ---
    def load_script(self):
        initial_dir = Path.cwd()
        filename = filedialog.askopenfilename(title="Open Tau Script", initialdir=initial_dir, filetypes=[("Tau Scripts", "*.tau"), ("All Files", "*.*")])
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f: content = f.read()
                self.script_lines = [line for line in content.splitlines()]
                self.current_step_index = 0
                
                self.show_script_viewer()
                
                self.script_view.config(state='normal')
                self.script_view.delete('1.0', tk.END)
                self.script_view.insert('1.0', content)
                self.script_view.config(state='disabled')
                
                if not any(line.strip() for line in self.script_lines):
                    messagebox.showinfo("Empty File", "File is empty."); return

                self.step_btn.config(state="normal")
                self.toggle_script_btn.config(state="normal")
                self.script_status.config(text=f"Loaded: {Path(filename).name}", fg=self.colors["primary"])
                self.log_to_widget("repl", f"--- Script Loaded: {Path(filename).name} ---", "info")
                self.highlight_current_line()
            except Exception as e: messagebox.showerror("Error", f"Failed to read file:\n{e}")

    def show_script_viewer(self):
        if not self.script_viewer_visible:
            self.paned.add(self.mid_frame, after=self.left_frame, minsize=250, width=300, stretch="never")
            self.script_viewer_visible = True

    def hide_script_viewer(self):
        if self.script_viewer_visible:
            self.paned.forget(self.mid_frame)
            self.script_viewer_visible = False

    def toggle_script_viewer(self):
        if self.script_viewer_visible:
            self.hide_script_viewer()
        else:
            self.show_script_viewer()

    def highlight_current_line(self):
        self.script_view.tag_remove("current_line", "1.0", tk.END)
        if self.current_step_index < len(self.script_lines):
            line_num = self.current_step_index + 1
            start, end = f"{line_num}.0", f"{line_num}.end"
            self.script_view.tag_add("current_line", start, end)
            self.script_view.see(start)

    def execute_next_step(self):
        while self.current_step_index < len(self.script_lines):
            line = self.script_lines[self.current_step_index].strip()
            if not line: self.current_step_index += 1
            else: break
        
        if self.current_step_index >= len(self.script_lines):
            self._finish_script(); return

        command = self.script_lines[self.current_step_index]
        stripped_cmd = command.strip()

        if stripped_cmd.startswith("#"):
            self.log_to_widget("repl", command, "comment")
            self.log_to_widget("history", f"» {command}") 
        else:
            self.send_command(command)

        self.current_step_index += 1
        
        temp_index = self.current_step_index
        while temp_index < len(self.script_lines):
            if self.script_lines[temp_index].strip(): break
            temp_index += 1
        
        if temp_index < len(self.script_lines):
             self.highlight_current_line()
             self.script_status.config(text=f"Step: {self.current_step_index}/{len(self.script_lines)}")
        else:
             self._finish_script()

    def _finish_script(self):
        self.script_status.config(text="Script finished", fg=self.colors["success"])
        self.step_btn.config(state="disabled")

    def send_command(self, command):
        if self.process and self.process.poll() is None:
            if command.strip().lower() in ["clear", "cls"]:
                self.repl_log.config(state='normal')
                self.repl_log.delete('1.0', tk.END)
                self.repl_log.config(state='disabled')
                try: self.process.stdin.write("\n"); self.process.stdin.flush()
                except Exception: pass
                return

            self.log_to_widget("history", f"» {command}")
            
            debug_data = {"time": datetime.now().strftime("%H:%M:%S.%f")[:-3], "type": "send", "text": command, "duration": 0}
            self.msg_queue.put(("debug_data", debug_data, None))
            
            self.command_start_time = time.monotonic()
            self.last_command = command
            try:
                self.process.stdin.write(command + "\n"); self.process.stdin.flush()
            except Exception as e: self.log_to_widget("repl", f"Error writing to process: {e}", "error")
        else: self.log_to_widget("repl", "Tau process is not running.", "error")

    def prompt_for_executable(self):
        filename = filedialog.askopenfilename(title="Select Tau Executable", filetypes=[("Executables", "*.exe"), ("All Files", "*.*")])
        if filename:
            self.tau_executable = filename
            save_tau_path(filename)
            self.log_to_widget("repl", f"Path updated to: {filename}", "info")
            self.restart_process()

    def restart_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate(); self.process = None
        self.log_to_widget("repl", "-"*30 + "\nRestarting Tau Process...\n" + "-"*30, "info")
        self.start_tau_thread()

    def update_stats(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.stats_label.config(text=f"CPU: {cpu:2.1f}%    RAM: {ram:2.1f}%")
        except: pass
        self.root.after(1000, self.update_stats)

    def log_to_widget(self, widget_name, text, tag=None):
        widget_map = {"repl": self.repl_log, "history": self.history_log}
        widget = widget_map.get(widget_name)
        if widget:
            widget.config(state='normal')
            if widget_name == "repl":
                # Look specifically for "tau>" anywhere in the string
                if tag is None and "tau>" in text:
                    parts = text.split("tau>", 1)
                    prefix = parts[0] + "tau>"  # Include the prompt
                    content = parts[1]
                    # Color the prompt part with 'prefix' tag
                    widget.insert(tk.END, prefix, "prefix")
                    # Insert the rest normally
                    widget.insert(tk.END, content + "\n")
                else:
                    widget.insert(tk.END, text + "\n", tag)
            else: 
                widget.insert(tk.END, text + "\n", tag)
            widget.see(tk.END); widget.config(state='disabled')

    def start_tau_thread(self):
        thread = threading.Thread(target=self._run_process, daemon=True)
        thread.start()

    def _run_process(self):
        if not self.tau_executable:
            self.msg_queue.put(("repl", "Error: Tau executable path not set.", "error")); return

        try:
            self.process = subprocess.Popen(self.tau_executable, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0)
            self.msg_queue.put(("repl", "▶ Tau REPL process started...", "info"))
            self.msg_queue.put(("debug_data", {"time": datetime.now().strftime("%H:%M:%S.%f")[:-3], "type": "info", "text": "PROCESS STARTED"}, None))
            
            while True:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None: break
                if line:
                    cleaned_line = strip_ansi_codes(line.strip())
                    if not cleaned_line: continue
                    if cleaned_line == "tau>": continue 
                    
                    is_echo = self.last_command is not None and cleaned_line == self.last_command
                    is_prompt_and_echo = self.last_command is not None and cleaned_line == f"tau> {self.last_command}"
                    if is_echo or is_prompt_and_echo:
                        if is_echo or is_prompt_and_echo: self.last_command = None
                        continue

                    duration = 0.0
                    if self.command_start_time:
                        duration = time.monotonic() - self.command_start_time
                        self.command_start_time = None

                    self.msg_queue.put(("repl", cleaned_line, None))
                    
                    self.msg_queue.put(("debug_data", {
                        "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        "type": "recv",
                        "text": cleaned_line,
                        "duration": duration
                    }, "recv"))
                    
        except Exception as e: self.msg_queue.put(("repl", f"Error: {e}", "error"))
        finally: 
            self.msg_queue.put(("debug_data", {"time": datetime.now().strftime("%H:%M:%S.%f")[:-3], "type": "info", "text": "PROCESS FINISHED"}, None))

    def check_queue(self):
        while not self.msg_queue.empty():
            try:
                target, message, tag = self.msg_queue.get_nowait()
                if target == "debug_data":
                    self.debug_events.append(message)
                    self.debug_log.config(state='normal')
                    self._append_debug_entry(message)
                    self.debug_log.see(tk.END)
                    self.debug_log.config(state='disabled')
                else:
                    self.log_to_widget(target, message, tag)
            except queue.Empty: pass
        self.root.after(100, self.check_queue)

    def on_submit(self, event):
        command = self.input_entry.get()
        if command:
            self.send_command(command)
            self.input_entry.delete(0, tk.END)
    
    # --- Theme Editor (Stub) ---
    def open_theme_editor(self):
        editor = tk.Toplevel(self.root)
        editor.title("Edit Theme")
        editor.geometry("650x700")
        editor.configure(bg=self.colors["bg_base"])
        editor.transient(self.root); editor.grab_set()
        container = tk.Frame(editor, bg=self.colors["bg_base"])
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        entries = {}
        keys = list(self.colors.keys())
        half = (len(keys) + 1) // 2
        for i, key in enumerate(keys):
            row = i % half; col = (i // half) * 3 
            lbl = tk.Label(container, text=key, bg=self.colors["bg_base"], fg=self.colors["fg_text"])
            lbl.grid(row=row, column=col, sticky="e", padx=5, pady=5)
            var = tk.StringVar(value=self.colors[key])
            entries[key] = var
            ent = tk.Entry(container, textvariable=var, width=10, bg=self.colors["bg_surface1"], fg=self.colors["fg_text"], insertbackground=self.colors["fg_text"])
            ent.grid(row=row, column=col+1, padx=5, pady=5)
            btn = tk.Button(container, text="⬛", bg=self.colors[key], fg=self.colors[key], command=lambda k=key, v=var, b=None: self._pick_color(k, v))
            btn.configure(command=lambda k=key, v=var, b=btn: self._pick_color(k, v, b))
            btn.grid(row=row, column=col+2, padx=5, pady=5)
        btn_frame = tk.Frame(editor, bg=self.colors["bg_base"])
        btn_frame.pack(fill=tk.X, pady=10, padx=20)
        def save_changes():
            new_colors = {}
            for k, v in entries.items():
                val = v.get().strip()
                if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', val): messagebox.showerror("Invalid Color", f"Invalid hex code for {k}: {val}"); return
                new_colors[k] = val
            self.colors = new_colors; self.apply_theme(); save_theme(self.colors); editor.destroy()
        def reset_defaults():
            if messagebox.askyesno("Reset Theme", "Revert to default Monokai colors?"):
                for k, v in DEFAULT_THEME.items(): 
                    if k in entries: entries[k].set(v)
        ttk.Button(btn_frame, text="Save & Apply", style="Action.TButton", command=save_changes).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", style="Action.TButton", command=editor.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Reset Defaults", style="Action.TButton", command=reset_defaults).pack(side=tk.LEFT, padx=5)

    def _pick_color(self, key, var, btn=None):
        color = colorchooser.askcolor(color=var.get(), title=f"Choose color for {key}")
        if color[1]:
            var.set(color[1])
            if btn: btn.configure(bg=color[1], fg=color[1])

if __name__ == "__main__":
    root = tk.Tk()
    app = TauGUI(root)
    root.mainloop()