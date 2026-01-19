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
from pathlib import Path
from datetime import datetime

# --- Default Theme (Semantic Names) ---
DEFAULT_THEME = {
    # --- Backgrounds & Text ---
    "bg_base": "#272822",        # Main Window Background
    "bg_surface0": "#272822",    # Panel Backgrounds
    "bg_surface1": "#3E3D32",    # Input Fields / Footer / Highlight
    "fg_text": "#F8F8F2",        # Main Text Color
    
    # --- Semantic Colors ---
    "primary": "#AE81FF",        # Script Header / "Tau responds:" / Focus
    "repl_header": "#435052",    # REPL Panel Header
    "history_header": "#A6E22E", # History Panel Header
    "debug_header": "#9CBEC5",   # Debug Panel Header
    
    "error": "#FF7979",          # Error messages
    "success": "#A6E22E",        # "Script finished" message
    "info": "#94BEC7",           # System info messages
    
    "debug_send": "#DA6792",     # Debug Log: Sent commands
    "debug_recv": "#BAA9DB",     # Debug Log: Received output
    
    "header_text": "#17170E",    # Dark text on colored headers (Contrast)
    
    # --- UI Elements ---
    "button_active": "#75715E",
    "scrollbar_bg": "#272822",
    "scrollbar_trough": "#17170E",
    "scrollbar_grip": "#75715E"
}

CONFIG_FILE = 'config.ini'

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
    """Loads theme from config, falls back to DEFAULT_THEME."""
    config = load_config()
    theme = DEFAULT_THEME.copy()
    
    if 'Theme' in config:
        for key in theme:
            if key in config['Theme']:
                theme[key] = config['Theme'][key]
    return theme

def save_theme(colors):
    """Saves the current colors to config.ini."""
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
        self.root.title("Tau Lang GUI")
        self.root.geometry("1400x800")
        
        # Load Theme
        self.colors = load_theme()
        self.root.configure(bg=self.colors["bg_base"])

        self.msg_queue = queue.Queue()
        self.process = None
        self.command_start_time = None
        self.last_command = None
        self.tau_executable = find_tau_executable()
        
        # --- Stepper State ---
        self.script_lines = []
        self.current_step_index = 0
        
        # --- UI Tracking for Theme Updates ---
        self.text_widgets = []
        self.frames = []
        self.labels = [] # Stores (widget, semantic_color_key)

        self._setup_styles()
        self._build_layout()
        
        # Apply initial theme
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

    def _update_ttk_styles(self):
        c = self.colors
        
        self.style.configure("TFrame", background=c["bg_base"])
        self.style.configure("TLabel", background=c["bg_base"], foreground=c["fg_text"])
        
        self.style.configure("Vertical.TScrollbar",
            background=c["scrollbar_grip"],
            troughcolor=c["scrollbar_trough"],
            bordercolor=c["bg_base"],
            arrowcolor=c["fg_text"],
            lightcolor=c["scrollbar_grip"],
            darkcolor=c["scrollbar_grip"]
        )
        self.style.map("Vertical.TScrollbar",
            background=[('active', c["button_active"]), ('pressed', c["primary"])]
        )

        self.style.configure("Action.TButton", 
            background=c["bg_surface1"], 
            foreground=c["fg_text"],
            borderwidth=1,
            focusthickness=3,
            focuscolor=c["primary"]
        )
        self.style.map("Action.TButton",
            background=[('active', c["button_active"]), ('disabled', c["header_text"])],
            foreground=[('disabled', c["bg_surface1"])]
        )

    def apply_theme(self):
        """Applies self.colors to all widgets using semantic names."""
        c = self.colors
        
        self.root.configure(bg=c["bg_base"])
        self._update_ttk_styles()

        # Update Text Widgets
        for widget in self.text_widgets:
            widget.configure(bg=c["bg_base"], fg=c["fg_text"], insertbackground=c["fg_text"])
            widget.tag_config("error", foreground=c["error"])
            widget.tag_config("info", foreground=c["info"])
            widget.tag_config("prefix", foreground=c["primary"])
            widget.tag_config("send", foreground=c["debug_send"])
            widget.tag_config("recv", foreground=c["debug_recv"])
            if widget == self.script_view:
                 widget.tag_config("current_line", background=c["bg_surface1"], foreground="#ffffff")

        # Update Inputs
        self.input_entry.configure(bg=c["bg_surface1"], fg=c["fg_text"], insertbackground=c["fg_text"])

        # Update Frames
        for frame in self.frames:
            frame.configure(bg=c["bg_base"])

        # Update Labels
        for label, color_key in self.labels:
            bg_color = c[color_key] if color_key in c else c["bg_base"]
            
            # Text color for headers needs to contrast
            if color_key in ["repl_header", "primary", "history_header", "debug_header"]:
                fg_color = c["header_text"]
            elif color_key == "bg_surface1":
                fg_color = c["fg_text"]
            else:
                fg_color = c["fg_text"]
                
            label.configure(bg=bg_color, fg=fg_color)
        
        self.paned.configure(bg=c["bg_base"])
        self.right_pane_vert.configure(bg=c["bg_base"])

    # --- Theme Editor Logic ---
    def open_theme_editor(self):
        editor = tk.Toplevel(self.root)
        editor.title("Edit Theme")
        editor.geometry("650x700")
        editor.configure(bg=self.colors["bg_base"])
        editor.transient(self.root)
        editor.grab_set()

        container = tk.Frame(editor, bg=self.colors["bg_base"])
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        entries = {}

        # 2-column grid
        keys = list(self.colors.keys())
        half = (len(keys) + 1) // 2
        
        for i, key in enumerate(keys):
            row = i % half
            col = (i // half) * 3 

            lbl = tk.Label(container, text=key, bg=self.colors["bg_base"], fg=self.colors["fg_text"])
            lbl.grid(row=row, column=col, sticky="e", padx=5, pady=5)

            var = tk.StringVar(value=self.colors[key])
            entries[key] = var
            
            ent = tk.Entry(container, textvariable=var, width=10, bg=self.colors["bg_surface1"], fg=self.colors["fg_text"], insertbackground=self.colors["fg_text"])
            ent.grid(row=row, column=col+1, padx=5, pady=5)

            # Color Picker Button
            btn = tk.Button(container, text="⬛", bg=self.colors[key], fg=self.colors[key], 
                            command=lambda k=key, v=var, b=None: self._pick_color(k, v))
            btn.configure(command=lambda k=key, v=var, b=btn: self._pick_color(k, v, b))
            btn.grid(row=row, column=col+2, padx=5, pady=5)

        # Buttons Frame
        btn_frame = tk.Frame(editor, bg=self.colors["bg_base"])
        btn_frame.pack(fill=tk.X, pady=10, padx=20)

        def save_changes():
            new_colors = {}
            for k, v in entries.items():
                val = v.get().strip()
                if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', val):
                    messagebox.showerror("Invalid Color", f"Invalid hex code for {k}: {val}")
                    return
                new_colors[k] = val
            
            self.colors = new_colors
            self.apply_theme()
            save_theme(self.colors)
            editor.destroy()

        def reset_defaults():
            if messagebox.askyesno("Reset Theme", "Revert to default Monokai colors?"):
                for k, v in DEFAULT_THEME.items():
                    if k in entries:
                        entries[k].set(v)

        ttk.Button(btn_frame, text="Save & Apply", style="Action.TButton", command=save_changes).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", style="Action.TButton", command=editor.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Reset Defaults", style="Action.TButton", command=reset_defaults).pack(side=tk.LEFT, padx=5)

    def _pick_color(self, key, var, btn):
        color = colorchooser.askcolor(color=var.get(), title=f"Choose color for {key}")
        if color[1]:
            var.set(color[1])
            if btn: btn.configure(bg=color[1], fg=color[1])

    # --- UI Building ---
    def _create_styled_text_widget(self, parent, height=None):
        container = tk.Frame(parent, bg=self.colors["bg_base"])
        self.frames.append(container)
        
        scrollbar = ttk.Scrollbar(container, orient="vertical", style="Vertical.TScrollbar")
        
        text_widget = tk.Text(
            container, 
            bg=self.colors["bg_base"], 
            fg=self.colors["fg_text"],
            insertbackground="white", 
            font=self.mono_font,
            state='disabled',
            height=height if height else 1,
            yscrollcommand=scrollbar.set,
            relief="flat",
            padx=5, pady=5
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
        
        # LEFT: Config & Exit
        self.config_btn = ttk.Button(top_bar, text="⚙ Config", style="Action.TButton", command=self.prompt_for_executable)
        self.config_btn.pack(side=tk.LEFT)

        self.exit_btn = ttk.Button(top_bar, text="Exit", style="Action.TButton", command=self.root.quit)
        self.exit_btn.pack(side=tk.LEFT, padx=5)

        # Theme Button
        self.theme_btn = ttk.Button(top_bar, text="🎨 Theme", style="Action.TButton", command=self.open_theme_editor)
        self.theme_btn.pack(side=tk.LEFT, padx=5)

        self.script_status = tk.Label(top_bar, text="No script loaded", font=self.ui_font)
        self.labels.append((self.script_status, "bg_base"))
        self.script_status.pack(side=tk.RIGHT, padx=10)

        self.step_btn = ttk.Button(top_bar, text="Step Next ▶", style="Action.TButton", state="disabled", command=self.execute_next_step)
        self.step_btn.pack(side=tk.RIGHT, padx=5)

        self.load_btn = ttk.Button(top_bar, text="📂 Load Script", style="Action.TButton", command=self.load_script)
        self.load_btn.pack(side=tk.RIGHT, padx=5)

        # --- Middle Split ---
        self.paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, bg=self.colors["bg_base"], sashwidth=4, sashrelief=tk.FLAT)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # COL 1
        self.left_frame = tk.Frame(self.paned)
        self.frames.append(self.left_frame)
        self.paned.add(self.left_frame, minsize=500, width=600, stretch="always")

        lbl_repl = tk.Label(self.left_frame, text="REPL Output")
        lbl_repl.pack(fill=tk.X)
        self.labels.append((lbl_repl, "repl_header"))

        repl_container, self.repl_log = self._create_styled_text_widget(self.left_frame)
        repl_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.input_entry = tk.Entry(self.left_frame, font=self.mono_font)
        self.input_entry.pack(fill=tk.X, ipady=5)
        self.input_entry.bind("<Return>", self.on_submit)

        # COL 2
        self.mid_frame = tk.Frame(self.paned)
        self.frames.append(self.mid_frame)
        
        lbl_script = tk.Label(self.mid_frame, text="Script Viewer")
        lbl_script.pack(fill=tk.X)
        self.labels.append((lbl_script, "primary"))

        script_container, self.script_view = self._create_styled_text_widget(self.mid_frame)
        script_container.pack(fill=tk.BOTH, expand=True)
        self.script_view.config(cursor="arrow")

        # COL 3
        self.right_frame = tk.Frame(self.paned)
        self.frames.append(self.right_frame)
        self.paned.add(self.right_frame, minsize=250, width=300, stretch="never")

        self.right_pane_vert = tk.PanedWindow(self.right_frame, orient=tk.VERTICAL, bg=self.colors["bg_base"], sashwidth=4)
        self.right_pane_vert.pack(fill=tk.BOTH, expand=True)

        hist_frame = tk.Frame(self.right_pane_vert)
        self.frames.append(hist_frame)
        self.right_pane_vert.add(hist_frame, height=200)
        
        lbl_hist = tk.Label(hist_frame, text="History")
        lbl_hist.pack(fill=tk.X)
        self.labels.append((lbl_hist, "history_header"))
        
        hist_container, self.history_log = self._create_styled_text_widget(hist_frame)
        hist_container.pack(fill=tk.BOTH, expand=True)

        debug_frame = tk.Frame(self.right_pane_vert)
        self.frames.append(debug_frame)
        self.right_pane_vert.add(debug_frame, height=200)
        
        lbl_debug = tk.Label(debug_frame, text="Debug Log")
        lbl_debug.pack(fill=tk.X)
        self.labels.append((lbl_debug, "debug_header"))
        
        debug_container, self.debug_log = self._create_styled_text_widget(debug_frame)
        debug_container.pack(fill=tk.BOTH, expand=True)

        # Footer
        footer_bar = tk.Frame(main_container)
        self.frames.append(footer_bar)
        footer_bar.pack(fill=tk.X, pady=(5, 0), side=tk.BOTTOM)

        self.stats_label = tk.Label(footer_bar, text="CPU: 0.0%  RAM: 0.0%", font=self.tiny_font)
        self.stats_label.pack(side=tk.RIGHT)
        self.labels.append((self.stats_label, "bg_surface1"))

    # --- Runtime Logic ---
    def load_script(self):
        initial_dir = Path.cwd()
        filename = filedialog.askopenfilename(title="Open Tau Script", initialdir=initial_dir, filetypes=[("Tau Scripts", "*.tau"), ("All Files", "*.*")])
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f: content = f.read()
                self.script_lines = [line for line in content.splitlines()]
                self.current_step_index = 0
                if str(self.mid_frame) not in self.paned.panes():
                    self.paned.add(self.mid_frame, after=self.left_frame, minsize=250, width=300, stretch="never")
                self.script_view.config(state='normal')
                self.script_view.delete('1.0', tk.END)
                self.script_view.insert('1.0', content)
                self.script_view.config(state='disabled')
                
                if not any(line.strip() for line in self.script_lines):
                    messagebox.showinfo("Empty File", "File is empty."); return

                self.step_btn.config(state="normal")
                self.script_status.config(text=f"Loaded: {Path(filename).name}", fg=self.colors["primary"])
                self.log_to_widget("repl", f"--- Script Loaded: {Path(filename).name} ---", "info")
                self.highlight_current_line()
            except Exception as e: messagebox.showerror("Error", f"Failed to read file:\n{e}")

    def close_script_viewer(self):
        self.script_view.config(state='normal')
        self.script_view.delete('1.0', tk.END)
        self.script_view.config(state='disabled')
        if str(self.mid_frame) in self.paned.panes(): self.paned.forget(self.mid_frame)

    def highlight_current_line(self):
        self.script_view.tag_remove("current_line", "1.0", tk.END)
        if self.current_step_index < len(self.script_lines):
            line_num = self.current_step_index + 1
            start, end = f"{line_num}.0", f"{line_num}.end"
            self.script_view.tag_add("current_line", start, end)
            self.script_view.see(start)

    def execute_next_step(self):
        while self.current_step_index < len(self.script_lines):
            if self.script_lines[self.current_step_index].strip(): break
            self.current_step_index += 1 
        
        if self.current_step_index >= len(self.script_lines):
            self._finish_script(); return

        command = self.script_lines[self.current_step_index]
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
        self.close_script_viewer()

    def send_command(self, command):
        if self.process and self.process.poll() is None:
            if command.strip().lower() in ["clear", "cls"]:
                self.repl_log.config(state='normal')
                self.repl_log.delete('1.0', tk.END)
                self.repl_log.config(state='disabled')
                try:
                    self.process.stdin.write("\n"); self.process.stdin.flush()
                except Exception: pass
                return

            self.log_to_widget("history", f"» {command}")
            self.log_to_widget("debug", f"[{datetime.now().time()}] ▶ SEND: {command}", "send")
            
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
            else: widget.insert(tk.END, text + "\n", tag)
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
            self.msg_queue.put(("debug", f"[{datetime.now().time()}] ▶ PROCESS STARTED", "info"))
            is_response_start = True
            while True:
                line = self.process.stdout.readline()
                if not line and self.process.poll() is not None: break
                if line:
                    cleaned_line = strip_ansi_codes(line.strip())
                    if not cleaned_line: continue
                    prompt_str = "tau>"
                    if cleaned_line == prompt_str: continue 
                    is_echo = self.last_command is not None and cleaned_line == self.last_command
                    is_prompt_and_echo = self.last_command is not None and cleaned_line == f"{prompt_str} {self.last_command}"
                    if is_echo or is_prompt_and_echo:
                        if is_echo or is_prompt_and_echo: self.last_command = None
                        is_response_start = True; continue

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
        except Exception as e: self.msg_queue.put(("repl", f"Error: {e}", "error"))
        finally: self.msg_queue.put(("debug", f"[{datetime.now().time()}] ■ PROCESS FINISHED", "info"))

    def check_queue(self):
        while not self.msg_queue.empty():
            try:
                target, message, tag = self.msg_queue.get_nowait()
                self.log_to_widget(target, message, tag)
            except queue.Empty: pass
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