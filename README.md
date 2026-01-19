# Tau Lang GUI Wrapper (WIP)

This project is a multi-panel Graphical User Interface (GUI) for interacting with the **[Tau-lang REPL](https://github.com/IDNI/tau-lang)**. Built with Python's Tkinter, it provides a user-friendly environment with separate panels for REPL interaction, command history, and a detailed debug log.

* **Multi-Panel Layout**: A clean interface with dedicated, scrollable panels for REPL output, command history, and a debug log.
* **System Stats**: A live display of your current CPU and RAM usage.
* **Debug & Timing**: The debug panel shows a timestamped log of every command sent to the Tau REPL and every response received, including execution time.
* **Easy Configuration**: Built-in file picker to locate your Tau executable and save it automatically.

---

## Requirements

* **Python 3.7+**
* **Tkinter** (Usually included with Python standard installations).
* The compiled **`tau` executable** from the [Tau-lang repository](https://github.com/IDNI/tau-lang).

---

## Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
    cd your-repo-name
    ```

2.  **Install the required Python libraries:**
    This project depends on `psutil` for system stats.
    ```bash
    pip install psutil
    ```
    *(Note: If you are on Linux and get an error about missing `tkinter`, you may need to install it via your package manager, e.g., `sudo apt-get install python3-tk`)*.

---

## Configuration & Usage

To run the GUI, the script must know where to find the `tau` executable. There are several ways to configure this.

### Option 1: GUI Configuration (Recommended)

When you run the application for the first time, if the `tau` executable is not found, the application will automatically open a file dialog asking you to locate it.

* Select your `tau` or `tau.exe` file.
* The path will be automatically saved to `config.ini` for future runs.
* You can change this path at any time via the menu bar: **File > Configure Tau Path...**

### Option 2: Configuration File (config.ini)

For a manual setting, you can edit the `config.ini` file directly.

1.  Open `config.ini` in a text editor.
2.  Set the value of `TauExecutable` to the full path of your tau executable.
    * *Important: Do not use quotes around the path.*

### Option 3: Command-Line Argument

You can provide the path directly when you run the script. This overrides the config file.

```bash
python tau_gui.py --tau-path "C:\path\to\your\tau.exe"