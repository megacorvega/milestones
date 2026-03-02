import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from datetime import datetime, timedelta
import json
import uuid
import re
import ctypes
import copy

try:
    from PIL import ImageGrab, Image # Import Image for high-quality resizing
except ImportError:
    ImageGrab = None
    Image = None

# --- Make Tkinter Crisp on High-DPI Displays (Windows) ---
try:
    # Tell Windows this app is DPI-aware so it doesn't blur/stretch it
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass # Fails safely on Mac/Linux or older Windows versions

# =======================================================================
# --- Setup & Bootstrapper ---
# =======================================================================

def requires_setup():
    """Returns True if we are outside a venv OR missing required libraries."""
    if sys.prefix == sys.base_prefix:
        return True
    try:
        import PIL
        import tkcalendar
        return False
    except ImportError:
        return True

def run_setup_window_and_relaunch():
    """Shows a console UI, creates the venv, installs packages, and relaunches."""
    import venv
    
    root = tk.Tk()
    root.title("Milestones Setup")
    root.geometry("550x350")
    
    # Center the setup window on the screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (550 // 2)
    y = (root.winfo_screenheight() // 2) - (350 // 2)
    root.geometry(f"+{x}+{y}")
    
    tk.Label(root, text="Initializing Environment & Dependencies", font=("Arial", 12, "bold")).pack(pady=10)
    
    # Terminal-like text output log
    log_text = tk.Text(root, state='disabled', bg="#1e1e1e", fg="#4af626", font=("Consolas", 10))
    log_text.pack(padx=15, pady=(0, 15), fill=tk.BOTH, expand=True)
    
    def log(msg):
        """Safely pushes log updates to the UI thread."""
        def _log():
            try:
                log_text.config(state='normal')
                log_text.insert(tk.END, msg + "\n")
                log_text.see(tk.END)
                log_text.config(state='disabled')
            except tk.TclError:
                pass # Window was destroyed
        root.after(0, _log)

    # Handle graceful exit if the user closes the setup window mid-install
    process_ref = []
    def on_closing():
        if process_ref and process_ref[0].poll() is None:
            try: process_ref[0].terminate()
            except: pass
        root.destroy()
        sys.exit(0)
        
    root.protocol("WM_DELETE_WINDOW", on_closing)

    def setup_thread():
        app_dir = os.path.dirname(os.path.abspath(__file__))
        venv_dir = os.path.join(app_dir, "venv")
        
        # Determine correct python paths for the new venv based on OS
        if os.name == 'nt':
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            venv_pythonw = os.path.join(venv_dir, "Scripts", "pythonw.exe")
            if not os.path.exists(venv_pythonw):
                venv_pythonw = venv_python
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            venv_pythonw = venv_python

        # 1. Ensure Venv exists
        if not os.path.exists(venv_dir):
            log("Creating virtual environment (venv)...")
            log("This may take a minute. Please wait.")
            try:
                venv.create(venv_dir, with_pip=True)
                log("Virtual environment successfully created.\n")
            except Exception as e:
                log(f"ERROR: Failed to create venv:\n{e}")
                return
        else:
            log("Virtual environment found.\n")

        # 2. Install dependencies
        log("Checking required packages (Pillow, tkcalendar)...")
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            
        try:
            process = subprocess.Popen(
                [venv_python, "-m", "pip", "install", "Pillow", "tkcalendar"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                **kwargs
            )
            process_ref.append(process)
            
            # REMOVED: The for loop that piped pip's output to the log.
            # Now we just wait for the silent installation to finish.
            process.wait()
            
            if process.returncode == 0:
                log("Packages verified successfully!")
                log("\n--- Setup Complete! ---")
                log("Starting application...")
                
                def launch_and_close():
                    subprocess.Popen([venv_pythonw, os.path.abspath(__file__)] + sys.argv[1:])
                    root.destroy()
                
                root.after(1500, launch_and_close)
            else:
                # If it fails, we can pull the error from stdout so the user knows what went wrong
                error_output = process.stdout.read()
                log(f"\nERROR: Failed to install dependencies. Please check your internet connection.\nDetails:\n{error_output}")
        except Exception as e:
            log(f"\nERROR: Subprocess failed:\n{e}")

    # Start the background installation thread so the UI doesn't freeze
    threading.Thread(target=setup_thread, daemon=True).start()
    root.mainloop()

# Run the bootstrapper and kill the base process so the venv process can take over
if requires_setup():
    run_setup_window_and_relaunch()
    sys.exit(0)

# =======================================================================
# --- Main Application Logic (Guaranteed to run inside configured venv) ---
# =======================================================================

try:
    from PIL import ImageGrab, Image
except ImportError:
    ImageGrab = None
    Image = None

try:
    from tkcalendar import Calendar
except ImportError:
    Calendar = None

SESSION_FILE = "session.json"

class ProjectTab(tk.Frame):
    """Encapsulates a single project schedule workspace."""
    def __init__(self, parent_notebook, app_controller):
        super().__init__(parent_notebook)
        self.notebook = parent_notebook
        self.app = app_controller
        self.file_path = None
        
        # --- Default Data ---
        self.project_name = "New Project"
        self.chart_title = "Project Timeline"
        self.start_date = datetime(2025, 1, 1)
        self.end_date = datetime(2026, 12, 30)
        self.milestones = [
            {"id": str(uuid.uuid4()), "name": "8\" Design", "start": datetime(2025, 1, 1), "days": 60, "color": "#f28e2b", "depends_on": None, "type": "normal"},
            {"id": str(uuid.uuid4()), "name": "8\" Prototyping", "start": datetime(2025, 3, 5), "days": 45, "color": "#5da5da", "depends_on": None, "type": "normal"}
        ]
        
        self.row_height = 50
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
        self.tooltip = None
        self.edge_margin = 10 
        self.resize_timer = None 
        
        self.setup_ui()
        self.push_history() # Hook for initial state
 
    def setup_ui(self):
        # --- Top Panel ---
        top_frame = tk.Frame(self, pady=10, padx=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        tk.Label(top_frame, text="Start:").pack(side=tk.LEFT)
        self.start_entry = tk.Entry(top_frame, width=10)
        self.start_entry.insert(0, self.start_date.strftime("%Y-%m-%d"))
        self.start_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(top_frame, text="End:").pack(side=tk.LEFT)
        self.end_entry = tk.Entry(top_frame, width=10)
        self.end_entry.insert(0, self.end_date.strftime("%Y-%m-%d"))
        self.end_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_frame, text="Update Dates", command=self.update_dates).pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_frame, text="+ Add Task", command=self.open_milestone_dialog, bg="#dff0d8").pack(side=tk.LEFT, padx=15)
        tk.Label(top_frame, text="(Drag labels to reorder)", fg="gray").pack(side=tk.LEFT)

        # Right side controls
        tk.Button(top_frame, text="X Close Tab", command=self.close_tab, bg="#f2dede").pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Export & Log", command=self.export_png, bg="#d9edf7").pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Save Project", command=self.save_project).pack(side=tk.RIGHT, padx=5)
        
        self.project_name_entry = tk.Entry(top_frame, width=15)
        self.project_name_entry.insert(0, self.project_name)
        self.project_name_entry.pack(side=tk.RIGHT, padx=(0, 5))
        tk.Label(top_frame, text="Project Name:").pack(side=tk.RIGHT)

        self.chart_title_entry = tk.Entry(top_frame, width=25)
        self.chart_title_entry.insert(0, self.chart_title)
        self.chart_title_entry.pack(side=tk.RIGHT, padx=(0, 15))
        tk.Label(top_frame, text="Display Title:").pack(side=tk.RIGHT)
        
        self.chart_title_entry.bind("<KeyRelease>", self.on_resize)
        
        # Hooks for autosave when user changes text boxes
        self.project_name_entry.bind("<FocusOut>", lambda e: self.push_history())
        self.chart_title_entry.bind("<FocusOut>", lambda e: self.push_history())

        # --- Canvas ---
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_stop)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Configure>", self.on_resize)
   
    # --- File & Tab Operations ---
    def get_app_dir(self): return os.path.dirname(os.path.abspath(__file__))

    def get_clean_project_name(self):
        raw_name = self.project_name_entry.get().strip()
        if not raw_name: raw_name = "Untitled_Project"
        return re.sub(r'[\\/*?:"<>|]', "", raw_name)

    def close_tab(self):
        self.app.close_tab(self)

    def save_project(self):
        if not self.file_path:
            self.file_path = filedialog.asksaveasfilename(
                parent=self,
                initialdir=self.get_app_dir(),
                initialfile=self.get_clean_project_name() + ".projects",
                defaultextension=".projects", 
                filetypes=[("Project Files", "*.projects"), ("All Files", "*.*")]
            )
        if not self.file_path: return
        
        self.autosave()
        messagebox.showinfo("Success", "Project saved successfully!", parent=self)
        self.app.save_session()  

    def load_from_file(self, path):
        try:
            with open(path, 'r') as f: data = json.load(f)
            self.file_path = path
            
            p_name = data.get("project_name", os.path.basename(path).replace(".projects", ""))
            self.project_name_entry.delete(0, tk.END)
            self.project_name_entry.insert(0, p_name)
            self.notebook.tab(self, text=p_name)
            
            c_title = data.get("chart_title", "Project Timeline")
            self.chart_title_entry.delete(0, tk.END)
            self.chart_title_entry.insert(0, c_title)
            
            self.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
            self.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d")
            self.start_entry.delete(0, tk.END)
            self.start_entry.insert(0, data["start_date"])
            self.end_entry.delete(0, tk.END)
            self.end_entry.insert(0, data["end_date"])
            
            self.milestones = []
            for task in data["milestones"]:
                task["start"] = datetime.strptime(task["start"], "%Y-%m-%d")
                if "id" not in task: task["id"] = str(uuid.uuid4())
                if "depends_on" not in task: task["depends_on"] = None
                if "type" not in task: task["type"] = "normal"
                self.milestones.append(task)
                
            self.resolve_dependencies()
            self.draw_chart()
            
            # Reset history baseline after loading
            self.undo_stack, self.redo_stack = [], []
            self.push_history()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load {path}:\n{e}", parent=self)

    def export_png(self):
        if Image is None:
            messagebox.showerror("Missing Library", "The 'Pillow' library is required to export images.", parent=self)
            return

        from PIL import ImageDraw, ImageFont
        import math

        proj_name = self.get_clean_project_name()
        app_dir = self.get_app_dir()
        base_img_path = os.path.join(app_dir, f"{proj_name}.png")
        archive_dir = os.path.join(app_dir, "archive")
        
        if os.path.exists(base_img_path):
            if not os.path.exists(archive_dir): os.makedirs(archive_dir)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(base_img_path, os.path.join(archive_dir, f"{proj_name}_{timestamp}.png"))

        try:
            scale = 3  
            width = self.canvas.winfo_width()
            if width < 100: width = 1100
            height = getattr(self, 'content_height', 200)
            
            img = Image.new('RGB', (int(width * scale), int(height * scale)), color='white')
            draw = ImageDraw.Draw(img)
            
            def s(val): return val * scale

            font_paths = ["arial.ttf", "Arial.ttf", "segoeui.ttf", "Helvetica.ttc", "LiberationSans-Regular.ttf"]
            font_title = font_normal = font_small = None
            for fp in font_paths:
                try:
                    font_title = ImageFont.truetype(fp, int(s(16)))
                    font_normal = ImageFont.truetype(fp, int(s(10)))
                    font_small = ImageFont.truetype(fp, int(s(8)))
                    break
                except IOError: continue
            
            if not font_title:
                font_title = font_normal = font_small = ImageFont.load_default()

            label_width = 170
            chart_x = label_width
            chart_width = width - label_width - 50 
            
            total_days = (self.end_date - self.start_date).days
            if total_days <= 0: total_days = 1
            pixels_per_day = chart_width / total_days
            
            title_text = self.chart_title_entry.get()
            draw.text((s(width / 2), s(25)), title_text, font=font_title, fill="#333", anchor="mm")
            
            y_shift = 40
            
            num_grid_lines = 6
            for i in range(num_grid_lines + 1):
                x = chart_x + (chart_width / num_grid_lines) * i
                grid_date = self.start_date + timedelta(days=(total_days / num_grid_lines) * i)
                draw.line([(s(x), s(20 + y_shift)), (s(x), s(height))], fill="#e8e8e8", width=int(s(1)))
                draw.text((s(x), s(15 + y_shift)), grid_date.strftime("%m/%d/%y"), font=font_normal, fill="#555", anchor="md")

            today = datetime.now()
            if self.start_date <= today <= self.end_date:
                exact_days_today = (today - self.start_date).total_seconds() / 86400.0
                today_x = chart_x + (exact_days_today * pixels_per_day)
                draw.line([(s(today_x), s(20 + y_shift)), (s(today_x), s(height))], fill="#d9534f", width=int(s(2)))
                draw.text((s(today_x), s(height - 10)), "Today", font=font_small, fill="#d9534f", anchor="mm")

            task_coords = {}
            y_offset = 80
            for idx, task in enumerate(self.milestones):
                task_type = task.get("type", "normal")
                
                draw.text((s(label_width - 10), s(y_offset + self.row_height/2)), task["name"], font=font_normal, fill="black", anchor="rm", align="right")
                
                exact_days_from_start = (task["start"] - self.start_date).total_seconds() / 86400.0
                x1 = chart_x + (exact_days_from_start * pixels_per_day)
                
                if task_type == "normal":
                    x2 = x1 + (task["days"] * pixels_per_day)
                    if x1 < chart_x: x1 = chart_x
                    if x2 > chart_x + chart_width: x2 = chart_x + chart_width
                    y1, y2 = y_offset + 5, y_offset + self.row_height - 5
                    
                    draw.rectangle([s(x1), s(y1), s(x2), s(y2)], fill=task["color"], outline="gray", width=int(s(1)))
                else:
                    if x1 < chart_x: x1 = chart_x
                    cy = y_offset + self.row_height / 2
                    
                    if task_type == "milestone":
                        cx = x1 + 5 + 14 # Match padding from draw_chart
                        x2 = cx + 14
                        points = []
                        for i in range(10):
                            angle = i * math.pi / 5 - math.pi / 2
                            r = 14 if i % 2 == 0 else 5.35
                            points.append((s(cx + r * math.cos(angle)), s(cy + r * math.sin(angle))))
                        draw.polygon(points, fill=task["color"], outline="black")
                    elif task_type == "completion":
                        pole_x = x1 + 5 # Match padding from draw_chart
                        x2 = pole_x + 18
                        pole_y_top = cy - 14
                        pole_y_bot = cy + 14
                        draw.line([(s(pole_x), s(pole_y_top)), (s(pole_x), s(pole_y_bot))], fill="black", width=int(s(2)))
                        draw.polygon([(s(pole_x), s(pole_y_top)), (s(pole_x + 18), s(cy - 4)), (s(pole_x), s(cy + 2))], fill=task["color"], outline="black")
                
                task_end_date = task["start"] + timedelta(days=task["days"])
                draw.text((s(x2 + 8), s(y_offset + self.row_height/2)), task_end_date.strftime("%m/%d/%y"), font=font_normal, fill="#555", anchor="lm")

                task_coords[task["id"]] = {"x1": x1, "x2": x2, "y1": y_offset + 5, "y2": y_offset + self.row_height - 5}
                y_offset += self.row_height

            for task in self.milestones:
                if task.get("depends_on") and task["depends_on"] in task_coords:
                    parent, child = task_coords[task["depends_on"]], task_coords[task["id"]]
                    p_x, p_y = max(parent["x1"] + 5, parent["x2"] - 15), parent["y2"]
                    c_x, c_y = child["x1"], child["y1"] + (child["y2"] - child["y1"]) / 2
                    
                    if c_y >= p_y:
                        points = [(s(p_x), s(p_y)), (s(p_x), s(c_y)), (s(c_x), s(c_y))]
                    else:
                        points = [(s(p_x), s(p_y)), (s(p_x), s(p_y + 10)), (s(c_x - 15), s(p_y + 10)), (s(c_x - 15), s(c_y)), (s(c_x), s(c_y))]
                    
                    draw.line(points, fill="#555555", width=int(s(2)))
                    
                    draw.polygon([
                        (s(c_x), s(c_y)), 
                        (s(c_x - 6), s(c_y - 4)), 
                        (s(c_x - 6), s(c_y + 4))
                    ], fill="#555555")

            img.save(base_img_path, "PNG", dpi=(300*scale, 300*scale))
            
            log_path = os.path.join(app_dir, f"{proj_name}.changelog")
            with open(log_path, "a") as log_file:
                log_file.write(f"--- Export Triggered: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                for task in self.milestones:
                    end_date = task["start"] + timedelta(days=task["days"])
                    log_file.write(f"- {task['name']}: {task['start'].strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n")
                log_file.write("\n")
                
            messagebox.showinfo("Success", f"'{proj_name}.png' saved!\nGenerated natively at {scale}x resolution.", parent=self)
            
        except Exception as e: 
            messagebox.showerror("Error", f"Failed to export:\n{e}", parent=self)
 
    # --- Core Chart Logic ---
    def update_dates(self):
        try:
            self.start_date = datetime.strptime(self.start_entry.get(), "%Y-%m-%d")
            self.end_date = datetime.strptime(self.end_entry.get(), "%Y-%m-%d")
            if self.end_date <= self.start_date: raise ValueError()
            self.draw_chart()
            self.push_history() # Hook
        except ValueError: messagebox.showerror("Date Error", "Format YYYY-MM-DD.\nEnd must be after Start.", parent=self)
   
    def resolve_dependencies(self):
        task_map = {t["id"]: t for t in self.milestones}
        changed = True
        loops = 0
        while changed and loops < 100: 
            changed = False
            for t in self.milestones:
                if t.get("depends_on") and t["depends_on"] in task_map:
                    parent = task_map[t["depends_on"]]
                    expected_start = parent["start"] + timedelta(days=parent["days"])
                    if t["start"] != expected_start:
                        t["start"] = expected_start
                        changed = True
            loops += 1

    def on_resize(self, event):
        """Debounces window resize events to prevent lag."""
        if self.resize_timer:
            self.after_cancel(self.resize_timer)
        self.resize_timer = self.after(100, self.draw_chart)

    def draw_chart(self):
        import math
        self.canvas.delete("all")
        self.canvas.update()
        
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 100: width = 1100 
        
        self.label_width = 170
        self.chart_x = self.label_width
        self.chart_width = width - self.label_width - 50 
        
        self.total_days = (self.end_date - self.start_date).days
        if self.total_days <= 0: self.total_days = 1
        self.pixels_per_day = self.chart_width / self.total_days
        
        title_text = self.chart_title_entry.get()
        self.canvas.create_text(width / 2, 25, text=title_text, font=("Arial", 16, "bold"), fill="#333")
        y_shift = 40
        
        num_grid_lines = 6
        for i in range(num_grid_lines + 1):
            x = self.chart_x + (self.chart_width / num_grid_lines) * i
            grid_date = self.start_date + timedelta(days=(self.total_days / num_grid_lines) * i)
            self.canvas.create_line(x, 20 + y_shift, x, height, fill="#e0e0e0", dash=(4, 4))
            self.canvas.create_text(x, 15 + y_shift, text=grid_date.strftime("%m/%d/%y"), anchor=tk.S, fill="#555")

        today = datetime.now()
        if self.start_date <= today <= self.end_date:
            exact_days_today = (today - self.start_date).total_seconds() / 86400.0
            today_x = self.chart_x + (exact_days_today * self.pixels_per_day)
            self.canvas.create_line(today_x, 20 + y_shift, today_x, height, fill="#d9534f", dash=(2, 2), width=2)
            self.canvas.create_text(today_x, height - 10, text="Today", fill="#d9534f", font=("Arial", 8, "bold"))

        task_coords = {}
        y_offset = 80
        for idx, task in enumerate(self.milestones):
            task_type = task.get("type", "normal")
            
            self.canvas.create_text(self.label_width - 10, y_offset + self.row_height/2, text=task["name"], 
                                    anchor=tk.E, justify=tk.RIGHT, font=("Arial", 10), width=self.label_width - 20, 
                                    tags=("label", f"task_{idx}"))
            
            exact_days_from_start = (task["start"] - self.start_date).total_seconds() / 86400.0
            x1 = self.chart_x + (exact_days_from_start * self.pixels_per_day)
            
            if task_type == "normal":
                x2 = x1 + (task["days"] * self.pixels_per_day)
                if x1 < self.chart_x: x1 = self.chart_x
                if x2 > self.chart_x + self.chart_width: x2 = self.chart_x + self.chart_width
                
                y1, y2 = y_offset + 5, y_offset + self.row_height - 5
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=task["color"], outline="gray", 
                                             tags=("drag_target", f"task_{idx}", f"task_{idx}_drag"))
            else:
                if x1 < self.chart_x: x1 = self.chart_x
                cy = y_offset + self.row_height / 2
                
                if task_type == "milestone":
                    cx = x1 + 5 + 14 # Add 5px padding past the arrow tip
                    x2 = cx + 14
                    
                    points = []
                    for i in range(10):
                        angle = i * math.pi / 5 - math.pi / 2
                        r = 14 if i % 2 == 0 else 5.35 # Fixed inner radius of 5.35 forces perfectly flat top lines
                        points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])
                    self.canvas.create_polygon(points, fill=task["color"], outline="black", 
                                               tags=("drag_target", f"task_{idx}", f"task_{idx}_drag"))
                elif task_type == "completion":
                    pole_x = x1 + 5 # Add 5px padding past the arrow tip
                    x2 = pole_x + 18
                    
                    pole_y_top = cy - 14
                    pole_y_bot = cy + 14
                    self.canvas.create_line(pole_x, pole_y_top, pole_x, pole_y_bot, fill="black", width=2, 
                                            tags=("drag_target", f"task_{idx}", f"task_{idx}_drag"))
                    self.canvas.create_polygon([pole_x, pole_y_top, pole_x + 18, cy - 4, pole_x, cy + 2], 
                                               fill=task["color"], outline="black", 
                                               tags=("drag_target", f"task_{idx}", f"task_{idx}_drag"))

            task_end_date = task["start"] + timedelta(days=task["days"])
            self.canvas.create_text(x2 + 8, y_offset + self.row_height/2, text=task_end_date.strftime("%m/%d/%y"), anchor=tk.W, font=("Arial", 9), fill="#555", tags=("date_text", f"date_{idx}"))

            # task_coords["x1"] remains the true start date so the arrows route perfectly up to it
            task_coords[task["id"]] = {"x1": x1, "x2": x2, "y1": y_offset + 5, "y2": y_offset + self.row_height - 5}
            y_offset += self.row_height
            
        self.content_height = y_offset + 20 
            
        for task in self.milestones:
            if task.get("depends_on") and task["depends_on"] in task_coords:
                parent, child = task_coords[task["depends_on"]], task_coords[task["id"]]
                p_x, p_y = max(parent["x1"] + 5, parent["x2"] - 15), parent["y2"]
                c_x, c_y = child["x1"], child["y1"] + (child["y2"] - child["y1"]) / 2
                
                points = [p_x, p_y, p_x, c_y, c_x, c_y] if c_y >= p_y else [p_x, p_y, p_x, p_y + 10, c_x - 15, p_y + 10, c_x - 15, c_y, c_x, c_y]
                self.canvas.create_line(*points, arrow=tk.LAST, fill="#555555", width=2, joinstyle=tk.MITER)

        self.canvas.config(scrollregion=(0, 0, width, y_offset + 50))    

    # --- Mouse Events ---
    def on_hover(self, event):
        item = self.canvas.find_withtag("current")
        if item and "drag_target" in self.canvas.gettags(item[0]):
            tags = self.canvas.gettags(item[0])
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            task_type = self.milestones[task_idx].get("type", "normal")
            
            if task_type == "normal":
                x1, _, x2, _ = self.canvas.bbox(f"task_{task_idx}_drag")
                self.canvas.config(cursor="sb_h_double_arrow" if abs(event.x - x1) < self.edge_margin or abs(event.x - x2) < self.edge_margin else "fleur")
            else:
                self.canvas.config(cursor="fleur")
        elif item and "label" in self.canvas.gettags(item[0]):
            self.canvas.config(cursor="sb_v_double_arrow") 
        elif item and "date_text" in self.canvas.gettags(item[0]):
             self.canvas.config(cursor="hand2")
        else: self.canvas.config(cursor="")

    def on_drag_start(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        
        # FIX: Ensure we don't accidentally try to turn "date_text" into an integer
        if "date_text" in tags:
            for tag in tags:
                if tag.startswith("date_") and tag != "date_text":
                    task_idx = int(tag.split("_")[1])
                    self.open_calendar_dialog(task_idx)
                    return

        if "label" in tags:
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            self.drag_data = {"item": item[0], "x": event.x, "task_idx": task_idx, "mode": "reorder", "tag": None}
            return

        if "drag_target" in tags:
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            tag = f"task_{task_idx}_drag"
            x1, y1, x2, y2 = self.canvas.bbox(tag)
            
            task_type = self.milestones[task_idx].get("type", "normal")
            mode = "move"
            
            if task_type == "normal":
                if abs(event.x - x1) < self.edge_margin: mode = "resize_left"
                elif abs(event.x - x2) < self.edge_margin: mode = "resize_right"
                
            if self.milestones[task_idx].get("depends_on") and mode in ["move", "resize_left"]: return 
            
            self.drag_data = {"item": item[0], "tag": tag, "x": event.x, "task_idx": task_idx, "mode": mode}

    def on_drag_motion(self, event):
        if not self.drag_data.get("item"): return
        mode = self.drag_data["mode"]
        
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = max(0, min(int((event.y - 80) / self.row_height), len(self.milestones))) 
            line_y = 80 + row_idx * self.row_height
            self.canvas.create_line(10, line_y, self.chart_x + self.chart_width, line_y, fill="blue", dash=(4, 4), tags="drop_line", width=2)
            return

        tag = self.drag_data["tag"]
        task_idx = self.drag_data["task_idx"]
        delta_x = event.x - self.drag_data["x"]
        
        bbox = self.canvas.bbox(tag)
        min_x, max_x, min_w = self.chart_x, self.chart_x + self.chart_width, max(5, self.pixels_per_day) 
        
        if mode == "move":
            if bbox[0] + delta_x < min_x: delta_x = min_x - bbox[0]
            elif bbox[2] + delta_x > max_x: delta_x = max_x - bbox[2]
            self.canvas.move(tag, delta_x, 0)
            self.drag_data["x"] += delta_x
        elif mode in ["resize_left", "resize_right"]:
            item = self.drag_data["item"]
            orig_x1, orig_y1, orig_x2, orig_y2 = self.canvas.coords(item)
            
            if mode == "resize_left":
                new_x1 = max(min_x, min(orig_x1 + delta_x, orig_x2 - min_w))
                self.canvas.coords(item, new_x1, orig_y1, orig_x2, orig_y2)
                self.drag_data["x"] = new_x1
            elif mode == "resize_right":
                new_x2 = min(max_x, max(orig_x2 + delta_x, orig_x1 + min_w))
                self.canvas.coords(item, orig_x1, orig_y1, new_x2, orig_y2)
                self.drag_data["x"] = new_x2

        bbox = self.canvas.bbox(tag)
        task_type = self.milestones[task_idx].get("type", "normal")
        
        # Snap BOTH ends so the visual tooltip is accurate while dragging
        if task_type == "normal":
            raw_start = self.start_date + timedelta(days=(bbox[0] - self.chart_x) / self.pixels_per_day)
            raw_end = self.start_date + timedelta(days=(bbox[2] - self.chart_x) / self.pixels_per_day)
            
            new_start = self.snap_to_weekday(raw_start)
            new_end = self.snap_to_weekday(raw_end)
            
            task_days = (new_end - new_start).total_seconds() / 86400.0
            if task_days < 1: task_days = 1
        else:
            raw_start = self.start_date + timedelta(days=(bbox[0] - 5 - self.chart_x) / self.pixels_per_day)
            new_start = self.snap_to_weekday(raw_start)
            task_days = 1 
            new_end = new_start + timedelta(days=task_days)
            
        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            
        t_text = f"Start: {new_start.strftime('%m/%d/%y')} | End: {new_end.strftime('%m/%d/%y')} | Days: {int(task_days)}"
        t_id = self.canvas.create_text(event.x, bbox[1] - 15, text=t_text, font=("Arial", 9, "bold"), fill="black")
        t_bbox = self.canvas.bbox(t_id)
        r_id = self.canvas.create_rectangle(t_bbox[0]-5, t_bbox[1]-2, t_bbox[2]+5, t_bbox[3]+2, fill="#ffffcc", outline="black")
        self.canvas.tag_raise(t_id)
        self.tooltip = {"text": t_id, "rect": r_id}

    def on_drag_stop(self, event):
        if not self.drag_data.get("item"): return
        mode = self.drag_data["mode"]
        
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = max(0, min(int((event.y - 80) / self.row_height), len(self.milestones)))
            old_idx = self.drag_data["task_idx"]
            if row_idx > old_idx: row_idx -= 1 
            if old_idx != row_idx:
                self.milestones.insert(row_idx, self.milestones.pop(old_idx))
            self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None, "tag": None}
            self.draw_chart()
            self.push_history() # Hook
            return

        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            self.tooltip = None
            
        tag = self.drag_data["tag"]
        task_idx = self.drag_data["task_idx"]
        bbox = self.canvas.bbox(tag)
        task_type = self.milestones[task_idx].get("type", "normal")
        
        # Save BOTH exact snapped ends
        if task_type == "normal":
            raw_start = self.start_date + timedelta(days=(bbox[0] - self.chart_x) / self.pixels_per_day)
            raw_end = self.start_date + timedelta(days=(bbox[2] - self.chart_x) / self.pixels_per_day)
            
            snapped_start = self.snap_to_weekday(raw_start)
            snapped_end = self.snap_to_weekday(raw_end)
            
            self.milestones[task_idx]["start"] = snapped_start
            days = (snapped_end - snapped_start).total_seconds() / 86400.0
            self.milestones[task_idx]["days"] = max(1, days)
        else:
            raw_start = self.start_date + timedelta(days=(bbox[0] - 5 - self.chart_x) / self.pixels_per_day)
            self.milestones[task_idx]["start"] = self.snap_to_weekday(raw_start)
            self.milestones[task_idx]["days"] = 1
            
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None, "tag": None}
        self.resolve_dependencies()
        self.draw_chart()
        self.push_history() # Hook 
   
    def on_double_click(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        for tag in self.canvas.gettags(item[0]):
            if tag.startswith("task_"):
                self.open_milestone_dialog(int(tag.split("_")[1]))
                break

    def on_date_click(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        
        for tag in tags:
            if tag.startswith("date_"):
                task_idx = int(tag.split("_")[1])
                self.open_calendar_dialog(task_idx)
                break

    def open_calendar_dialog(self, task_idx):
        task = self.milestones[task_idx]
        if task.get("type", "normal") != "normal":
            messagebox.showinfo("Fixed Duration", "Milestone and Completion events are fixed at 1 day.", parent=self)
            return

        current_end = task["start"] + timedelta(days=task["days"])

        dialog = tk.Toplevel(self)
        dialog.title(f"Set End Date: {task['name']}")
        dialog.geometry(f"280x250+{self.winfo_rootx() + self.winfo_width()//2 - 140}+{self.winfo_rooty() + self.winfo_height()//2 - 125}")
        dialog.transient(self)
        dialog.grab_set()

        cal = Calendar(dialog, selectmode='day', year=current_end.year, month=current_end.month, day=current_end.day,
                       weekendbackground='#f0f0f0', weekendforeground='#b0b0b0')
        cal.pack(pady=10, padx=10, fill="both", expand=True)

        def save_date():
            selected_date = cal.selection_get() 
            if selected_date.weekday() >= 5:
                messagebox.showwarning("Invalid Date", "Weekends cannot be selected. Please pick a weekday.", parent=dialog)
                return

            new_end_datetime = datetime.combine(selected_date, datetime.min.time())
            if new_end_datetime <= task["start"]:
                messagebox.showwarning("Invalid Date", "The end date must be after the start date.", parent=dialog)
                return
            
            new_days = (new_end_datetime - task["start"]).total_seconds() / 86400.0
            if new_days < 1:
                messagebox.showwarning("Invalid Date", "Tasks must be at least 1 day long.", parent=dialog)
                return
                
            self.milestones[task_idx]["days"] = new_days
            self.resolve_dependencies()
            self.draw_chart()
            self.push_history() # Hook
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Save", command=save_date, width=10, bg="#dff0d8").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
 
    def open_milestone_dialog(self, task_idx=None):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Task" if task_idx is not None else "Add Task")
        dialog.geometry(f"300x300+{self.winfo_rootx() + self.winfo_width()//2 - 150}+{self.winfo_rooty() + self.winfo_height()//2 - 150}")
        dialog.transient(self)
        dialog.grab_set() 
        
        cur_name, cur_color = "New Task", "#5da5da"
        cur_type = "Normal"
        if task_idx is not None:
            cur_name, cur_color = self.milestones[task_idx]["name"], self.milestones[task_idx]["color"]
            t_type = self.milestones[task_idx].get("type", "normal")
            if t_type == "milestone": cur_type = "Milestone"
            elif t_type == "completion": cur_type = "Completion"

        tk.Label(dialog, text="Task Name:").pack(pady=(10, 0))
        name_entry = tk.Entry(dialog, width=30)
        name_entry.insert(0, cur_name)
        name_entry.pack(pady=5)

        tk.Label(dialog, text="Task Type:").pack(pady=(5, 0))
        type_var = tk.StringVar(value=cur_type)
        type_combo = ttk.Combobox(dialog, textvariable=type_var, values=["Normal", "Milestone", "Completion"], state="readonly")
        type_combo.pack(pady=5)
        
        color_var = tk.StringVar(value=cur_color)
        def pick_color():
            c = colorchooser.askcolor(title="Choose color", initialcolor=color_var.get())[1]
            if c:
                color_var.set(c)
                color_btn.config(bg=c)

        tk.Label(dialog, text="Task Color:").pack(pady=(5, 0))
        color_btn = tk.Button(dialog, text="Pick Color", command=pick_color, bg=cur_color, width=15)
        color_btn.pack(pady=5)
        
        tk.Label(dialog, text="Depends On (Starts after):").pack(pady=(5, 0))
        dep_var = tk.StringVar()
        options, task_ids = ["None"], [""]
        for i, t in enumerate(self.milestones):
            if i != task_idx: 
                options.append(t["name"])
                task_ids.append(t["id"])
                
        dep_combo = ttk.Combobox(dialog, textvariable=dep_var, values=options, state="readonly")
        cur_dep = "None"
        if task_idx is not None and self.milestones[task_idx].get("depends_on"):
            dep_id = self.milestones[task_idx]["depends_on"]
            if dep_id in task_ids: cur_dep = options[task_ids.index(dep_id)]
        
        dep_combo.set(cur_dep)
        dep_combo.pack(pady=5)
        
        def save():
            if not name_entry.get().strip(): return messagebox.showwarning("Warning", "Name cannot be empty.", parent=dialog)
            sel_idx = options.index(dep_var.get())
            dep_id = task_ids[sel_idx] if sel_idx > 0 else None
            t_type = type_var.get().lower()
                
            if task_idx is not None:
                new_days = self.milestones[task_idx]["days"]
                if t_type != "normal": new_days = 1 
                self.milestones[task_idx].update({
                    "name": name_entry.get().strip(), "color": color_var.get(), 
                    "depends_on": dep_id, "type": t_type, "days": new_days
                })
            else:
                self.milestones.append({
                    "id": str(uuid.uuid4()), "name": name_entry.get().strip(), 
                    "start": self.start_date + timedelta(days=10), "days": 30 if t_type == "normal" else 1, 
                    "color": color_var.get(), "depends_on": dep_id, "type": t_type
                })
            self.resolve_dependencies()
            self.draw_chart()
            self.push_history() # Hook
            dialog.destroy()

        def delete():
            if messagebox.askyesno("Confirm", "Delete this task?", parent=dialog):
                deleted_id = self.milestones[task_idx]["id"]
                del self.milestones[task_idx]
                for t in self.milestones:
                    if t.get("depends_on") == deleted_id: t["depends_on"] = None 
                self.draw_chart()
                self.push_history() # Hook
                dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Save", command=save, width=8).pack(side=tk.LEFT, padx=5)
        if task_idx is not None: tk.Button(btn_frame, text="Delete", command=delete, fg="red", width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=5)

    def snap_to_weekday(self, dt):
        """Rounds to the nearest day, then forces it to a weekday."""
        # 1. Round to nearest whole day to fix fractional pixel offsets during drag
        dt_rounded = datetime(dt.year, dt.month, dt.day)
        if dt.hour >= 12:
            dt_rounded += timedelta(days=1)
            
        # 2. Snap away from weekends
        if dt_rounded.weekday() == 5: # Saturday
            return dt_rounded - timedelta(days=1)
        elif dt_rounded.weekday() == 6: # Sunday
            return dt_rounded + timedelta(days=1)
        return dt_rounded

# --- Undo/Redo & Autosave Logic ---
    def get_state_snapshot(self):
        """Creates a deep copy of the current project state."""
        return {
            "milestones": copy.deepcopy(self.milestones),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "project_name": self.project_name_entry.get(),
            "chart_title": self.chart_title_entry.get()
        }

    def restore_state(self, state):
        """Restores the UI and data to a provided state snapshot."""
        self.milestones = copy.deepcopy(state["milestones"])
        self.start_date = state["start_date"]
        self.end_date = state["end_date"]
        
        self.project_name_entry.delete(0, tk.END)
        self.project_name_entry.insert(0, state["project_name"])
        
        self.chart_title_entry.delete(0, tk.END)
        self.chart_title_entry.insert(0, state["chart_title"])
        
        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0, self.start_date.strftime("%Y-%m-%d"))
        
        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0, self.end_date.strftime("%Y-%m-%d"))
        
        self.resolve_dependencies()
        self.draw_chart()
        self.autosave()

    def push_history(self):
        """Saves the current state to the undo stack and triggers an autosave."""
        if not hasattr(self, 'undo_stack'):
            self.undo_stack, self.redo_stack = [], []
            
        new_state = self.get_state_snapshot()
        # Prevent duplicate sequential states
        if self.undo_stack and self.undo_stack[-1] == new_state:
            return
            
        self.undo_stack.append(new_state)
        self.redo_stack.clear()
        self.autosave()

    def undo(self):
        if len(self.undo_stack) > 1:
            current_state = self.undo_stack.pop()
            self.redo_stack.append(current_state)
            self.restore_state(self.undo_stack[-1])
            
    def redo(self):
        if self.redo_stack:
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            self.restore_state(next_state)

    def autosave(self):
        """Silently saves the project if it has an established file path."""
        if not self.file_path: return # Don't autosave untitled/unsaved projects
        
        data = {
            "project_name": self.project_name_entry.get(),
            "chart_title": self.chart_title_entry.get(),
            "start_date": self.start_date.strftime("%Y-%m-%d"), 
            "end_date": self.end_date.strftime("%Y-%m-%d"), 
            "milestones": []
        }
        for task in self.milestones:
            t = task.copy()
            t["start"] = task["start"].strftime("%Y-%m-%d")
            data["milestones"].append(t)
            
        try:
            with open(self.file_path, 'w') as f: json.dump(data, f, indent=4)
            self.notebook.tab(self, text=self.project_name_entry.get())
        except Exception: pass

class GanttApp(tk.Tk):
    """The main application wrapper managing tabs and session data."""
    def __init__(self):
        super().__init__()
        self.title("Milestones v0.1")
        self.geometry("1150x650")
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.setup_global_toolbar()
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        self.welcome_frame = tk.Frame(self)
        tk.Label(self.welcome_frame, text="Advanced Project Scheduler", font=("Arial", 16, "bold")).pack(pady=(100, 20))
        tk.Button(self.welcome_frame, text="Create New Project", font=("Arial", 12), bg="#dff0d8", command=self.new_project, width=20, pady=10).pack(pady=10)
        tk.Button(self.welcome_frame, text="Load Existing Project", font=("Arial", 12), command=self.load_project, width=20, pady=10).pack(pady=10)

        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.check_ui_state())
        
        self.load_session()
        self.check_ui_state()

    def setup_global_toolbar(self):
        toolbar = tk.Frame(self, bg="#e8e8e8", bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Button(toolbar, text="📄 New Project", command=self.new_project, relief=tk.FLAT, bg="#e8e8e8").pack(side=tk.LEFT, padx=5, pady=2)
        tk.Button(toolbar, text="📂 Load Project", command=self.load_project, relief=tk.FLAT, bg="#e8e8e8").pack(side=tk.LEFT, padx=5, pady=2)

    def check_ui_state(self):
        if len(self.notebook.tabs()) == 0:
            self.notebook.pack_forget()
            self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.welcome_frame.pack_forget()
            self.notebook.pack(fill=tk.BOTH, expand=True)

    def new_project(self):
        tab = ProjectTab(self.notebook, self)
        self.notebook.add(tab, text="New Project")
        self.notebook.select(tab)
        tab.draw_chart() 
        self.check_ui_state()
        self.save_session()

    def load_project(self):
        file_path = filedialog.askopenfilename(
            parent=self,
            initialdir=os.path.dirname(os.path.abspath(__file__)),
            filetypes=[("Project Files", "*.projects"), ("All Files", "*.*")]
        )
        if file_path: self.open_file_in_tab(file_path)

    def open_file_in_tab(self, file_path):
        for tab_id in self.notebook.tabs():
            tab_widget = self.nametowidget(tab_id)
            if hasattr(tab_widget, 'file_path') and tab_widget.file_path == file_path:
                self.notebook.select(tab_id)
                return

        tab = ProjectTab(self.notebook, self)
        self.notebook.add(tab, text="Loading...")
        self.notebook.select(tab)
        tab.load_from_file(file_path)
        self.check_ui_state()
        self.save_session()

    def close_tab(self, tab_frame):
        self.notebook.forget(tab_frame)
        tab_frame.destroy()
        self.check_ui_state()
        self.save_session()

    def save_session(self):
        open_files = []
        for tab_id in self.notebook.tabs():
            tab_widget = self.nametowidget(tab_id)
            if hasattr(tab_widget, 'file_path') and tab_widget.file_path:
                open_files.append(tab_widget.file_path)
        
        session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SESSION_FILE)
        try:
            with open(session_path, 'w') as f: json.dump({"open_files": open_files}, f)
        except Exception: pass 

    def load_session(self):
        session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SESSION_FILE)
        if os.path.exists(session_path):
            try:
                with open(session_path, 'r') as f:
                    open_files = json.load(f).get("open_files", [])
                    for path in open_files:
                        if os.path.exists(path):
                            self.open_file_in_tab(path)
            except Exception: pass

    def on_closing(self):
        self.save_session()
        self.destroy()

if __name__ == "__main__":
    app = GanttApp()
    app.mainloop()