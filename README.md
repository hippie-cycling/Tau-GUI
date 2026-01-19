# Tau Lang GUI Wrapper

This project is a feature-rich Graphical User Interface (GUI) for interacting with the **[Tau-lang REPL](https://github.com/IDNI/tau-lang)**. Built with Python's Tkinter, it transforms the command-line experience into a modern, customizable environment with debugging tools and script execution capabilities.


## Features

### 🖥️ Modern GUI Layout
* **Three-Pane Interface**:
    * **Left**: Main REPL interaction window.
    * **Middle**: Dynamic **Script Viewer** (appears when a script is loaded).
    * **Right**: Command History and detailed Debug Log.
* **System Stats**: Live CPU and RAM usage monitoring in the footer.

### 🎨 Fully Customizable Themes
* **Theme Editor**: Built-in graphical editor to change the color of every UI element.
* **Presets**: Comes with a polished **Monokai** dark theme by default.
* **Persistency**: Your custom color schemes are automatically saved to `config.ini`.

### ⏯️ Script Debugger (Stepper)
* **Load Scripts**: Open `.tau` files directly from the interface.
* **Step-by-Step Execution**: Execute your script line-by-line using the **"Step Next ▶"** button.
* **Visual Tracking**: The current line to be executed is highlighted in the script viewer.

### 🛠️ Developer Tools
* **Debug Log**: Timestamped log of exactly what is sent to and received from the Tau process (including execution time).
* **Smart Filtering**: Automatically cleans up raw REPL output (removing echoes and prompts) for a cleaner reading experience.
* **Clear Command**: Supports typing `clear` or `cls` to wipe the REPL screen.

---

## Requirements

* **Python 3.7+**
* **Tkinter** (Included with standard Python installations)
* The compiled **`tau` executable** from the [Tau-lang repository](https://github.com/IDNI/tau-lang).

---

## Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/tau-gui.git](https://github.com/your-username/tau-gui.git)
    cd tau-gui
    ```

2.  **Install dependencies:**
    ```bash
    pip install psutil
    ```
    *(Note: On some Linux distributions, you may need to install Tkinter separately: `sudo apt-get install python3-tk`)*

---

## Configuration

The application needs to know where your `tau` executable is located.

1.  **First Run**: When you launch the app, if `tau` is not found, it will automatically prompt you to select the executable file.
2.  **Manual Change**: You can change the path at any time by clicking the **"⚙ Config"** button in the top toolbar.
3.  **Config File**: The path is saved in `config.ini`:
    ```ini
    [Paths]
    TauExecutable = C:\Path\To\your\tau.exe
    ```

---

## Usage

Run the application:
```bash
python tau_gui.py