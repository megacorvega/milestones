import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from datetime import datetime, timedelta
import json
import os
import uuid
import re
from PIL import ImageGrab # Requires: pip install Pillow

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
        self.start_date = datetime(2025, 1, 1)
        self.end_date = datetime(2026, 12, 30)
        self.milestones = [
            {"id": str(uuid.uuid4()), "name": "8\" Design", "start": datetime(2025, 1, 1), "days": 60, "color": "#f28e2b", "depends_on": None},
            {"id": str(uuid.uuid4()), "name": "8\" Prototyping", "start": datetime(2025, 3, 5), "days": 45, "color": "#5da5da", "depends_on": None}
        ]
        
        self.row_height = 50
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
        self.tooltip = None
        self.edge_margin = 10 
        self.resize_timer = None # For debouncing window resizes
        
        self.setup_ui()

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
        
        tk.Button(top_frame, text="+ Add Milestone", command=self.open_milestone_dialog, bg="#dff0d8").pack(side=tk.LEFT, padx=15)
        tk.Label(top_frame, text="(Drag labels to reorder)", fg="gray").pack(side=tk.LEFT)

        # Right side controls
        tk.Button(top_frame, text="X Close Tab", command=self.close_tab, bg="#f2dede").pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Export & Log", command=self.export_png, bg="#d9edf7").pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Save Project", command=self.save_project).pack(side=tk.RIGHT, padx=5)
        
        self.project_name_entry = tk.Entry(top_frame, width=15)
        self.project_name_entry.insert(0, self.project_name)
        self.project_name_entry.pack(side=tk.RIGHT, padx=(0, 5))
        tk.Label(top_frame, text="Project Name:").pack(side=tk.RIGHT)

        # --- Canvas ---
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_stop)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<Configure>", self.on_resize) # Trigger redraw on resize

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
                initialdir=self.get_app_dir(),
                initialfile=self.get_clean_project_name() + ".projects",
                defaultextension=".projects", 
                filetypes=[("Project Files", "*.projects"), ("All Files", "*.*")]
            )
        if not self.file_path: return
        
        data = {
            "project_name": self.project_name_entry.get(),
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
            messagebox.showinfo("Success", "Project saved successfully!")
            self.notebook.tab(self, text=self.project_name_entry.get())
            self.app.save_session() 
        except Exception as e: messagebox.showerror("Error", f"Failed to save:\n{e}")

    def load_from_file(self, path):
        try:
            with open(path, 'r') as f: data = json.load(f)
            self.file_path = path
            
            p_name = data.get("project_name", os.path.basename(path).replace(".projects", ""))
            self.project_name_entry.delete(0, tk.END)
            self.project_name_entry.insert(0, p_name)
            self.notebook.tab(self, text=p_name)
            
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
                self.milestones.append(task)
                
            self.resolve_dependencies()
            self.draw_chart()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load {path}:\n{e}")

    def export_png(self):
        proj_name = self.get_clean_project_name()
        app_dir = self.get_app_dir()
        base_img_path = os.path.join(app_dir, f"{proj_name}.png")
        archive_dir = os.path.join(app_dir, "archive")
        
        if os.path.exists(base_img_path):
            if not os.path.exists(archive_dir): os.makedirs(archive_dir)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(base_img_path, os.path.join(archive_dir, f"{proj_name}_{timestamp}.png"))

        self.update_idletasks()
        x, y = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        x1 = x + self.canvas.winfo_width()
        
        # Auto-crop logic using tracked content height
        img_height = getattr(self, 'content_height', 200) 
        y1 = y + img_height
        
        try:
            ImageGrab.grab(bbox=(x, y, x1, y1)).save(base_img_path)
            log_path = os.path.join(app_dir, f"{proj_name}.changelog")
            with open(log_path, "a") as log_file:
                log_file.write(f"--- Export Triggered: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                for task in self.milestones:
                    end_date = task["start"] + timedelta(days=task["days"])
                    log_file.write(f"- {task['name']}: {task['start'].strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n")
                log_file.write("\n")
            messagebox.showinfo("Success", f"'{proj_name}.png' saved!\nAutomatically cropped to content.")
        except Exception as e: messagebox.showerror("Error", f"Failed to export:\n{e}")

    # --- Core Chart Logic ---
    def update_dates(self):
        try:
            self.start_date = datetime.strptime(self.start_entry.get(), "%Y-%m-%d")
            self.end_date = datetime.strptime(self.end_entry.get(), "%Y-%m-%d")
            if self.end_date <= self.start_date: raise ValueError()
            self.draw_chart()
        except ValueError: messagebox.showerror("Date Error", "Format YYYY-MM-DD. End must be after Start.")

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
        
        num_grid_lines = 6
        for i in range(num_grid_lines + 1):
            x = self.chart_x + (self.chart_width / num_grid_lines) * i
            grid_date = self.start_date + timedelta(days=(self.total_days / num_grid_lines) * i)
            self.canvas.create_line(x, 20, x, height, fill="#e0e0e0", dash=(4, 4))
            self.canvas.create_text(x, 15, text=grid_date.strftime("%m/%d/%y"), anchor=tk.S, fill="#555")

        today = datetime.now()
        if self.start_date <= today <= self.end_date:
            exact_days_today = (today - self.start_date).total_seconds() / 86400.0
            today_x = self.chart_x + (exact_days_today * self.pixels_per_day)
            self.canvas.create_line(today_x, 20, today_x, height, fill="#d9534f", dash=(2, 2), width=2)
            self.canvas.create_text(today_x, height - 10, text="Today", fill="#d9534f", font=("Arial", 8, "bold"))

        task_coords = {}
        y_offset = 40
        for idx, task in enumerate(self.milestones):
            self.canvas.create_text(self.label_width - 10, y_offset + self.row_height/2, text=task["name"], 
                                    anchor=tk.E, font=("Arial", 10), width=self.label_width - 20, 
                                    tags=("label", f"task_{idx}"))
            
            exact_days_from_start = (task["start"] - self.start_date).total_seconds() / 86400.0
            x1 = self.chart_x + (exact_days_from_start * self.pixels_per_day)
            x2 = x1 + (task["days"] * self.pixels_per_day)
            
            if x1 < self.chart_x: x1 = self.chart_x
            if x2 > self.chart_x + self.chart_width: x2 = self.chart_x + self.chart_width
            
            y1, y2 = y_offset + 5, y_offset + self.row_height - 5
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=task["color"], outline="gray", tags=("bar", f"task_{idx}"))
            task_coords[task["id"]] = {"x1": x1, "x2": x2, "y1": y1, "y2": y2}
            y_offset += self.row_height
            
        self.content_height = y_offset + 20 # Save for auto-crop export
            
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
        if item and "bar" in self.canvas.gettags(item[0]):
            x1, _, x2, _ = self.canvas.coords(item[0])
            self.canvas.config(cursor="sb_h_double_arrow" if abs(event.x - x1) < self.edge_margin or abs(event.x - x2) < self.edge_margin else "fleur")
        elif item and "label" in self.canvas.gettags(item[0]):
             self.canvas.config(cursor="sb_v_double_arrow") 
        else: self.canvas.config(cursor="")

    def on_drag_start(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        
        if "label" in tags:
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            self.drag_data = {"item": item[0], "x": event.x, "task_idx": task_idx, "mode": "reorder"}
            return

        if "bar" in tags:
            x1, _, x2, _ = self.canvas.coords(item[0])
            mode = "move"
            if abs(event.x - x1) < self.edge_margin: mode = "resize_left"
            elif abs(event.x - x2) < self.edge_margin: mode = "resize_right"
                
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            if self.milestones[task_idx].get("depends_on") and mode in ["move", "resize_left"]: return 
            
            self.drag_data = {"item": item[0], "x": event.x, "task_idx": task_idx, "mode": mode}

    def on_drag_motion(self, event):
        if not self.drag_data["item"]: return
        mode = self.drag_data["mode"]
        
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = max(0, min(int((event.y - 40) / self.row_height), len(self.milestones))) 
            line_y = 40 + row_idx * self.row_height
            self.canvas.create_line(10, line_y, self.chart_x + self.chart_width, line_y, fill="blue", dash=(4, 4), tags="drop_line", width=2)
            return

        item = self.drag_data["item"]
        delta_x = event.x - self.drag_data["x"]
        x1, y1, x2, y2 = self.canvas.coords(item)
        min_x, max_x, min_w = self.chart_x, self.chart_x + self.chart_width, 5 
        
        if mode == "move":
            if x1 + delta_x < min_x: delta_x = min_x - x1
            elif x2 + delta_x > max_x: delta_x = max_x - x2
            self.canvas.move(item, delta_x, 0)
            self.drag_data["x"] += delta_x
        elif mode == "resize_left":
            new_x1 = max(min_x, min(x1 + delta_x, x2 - min_w))
            self.canvas.coords(item, new_x1, y1, x2, y2)
            self.drag_data["x"] = new_x1
        elif mode == "resize_right":
            new_x2 = min(max_x, max(x2 + delta_x, x1 + min_w))
            self.canvas.coords(item, x1, y1, new_x2, y2)
            self.drag_data["x"] = new_x2

        coords = self.canvas.coords(item)
        new_start = self.start_date + timedelta(days=(coords[0] - self.chart_x) / self.pixels_per_day)
        task_days = (coords[2] - coords[0]) / self.pixels_per_day
        new_end = new_start + timedelta(days=task_days)
        
        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            
        t_text = f"Start: {new_start.strftime('%m/%d/%y')} | End: {new_end.strftime('%m/%d/%y')} | Days: {int(task_days)}"
        t_id = self.canvas.create_text(event.x, coords[1] - 15, text=t_text, font=("Arial", 9, "bold"), fill="black")
        bbox = self.canvas.bbox(t_id)
        r_id = self.canvas.create_rectangle(bbox[0]-5, bbox[1]-2, bbox[2]+5, bbox[3]+2, fill="#ffffcc", outline="black")
        self.canvas.tag_raise(t_id)
        self.tooltip = {"text": t_id, "rect": r_id}

    def on_drag_stop(self, event):
        if not self.drag_data["item"]: return
        mode = self.drag_data["mode"]
        
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = max(0, min(int((event.y - 40) / self.row_height), len(self.milestones)))
            old_idx = self.drag_data["task_idx"]
            if row_idx > old_idx: row_idx -= 1 
            if old_idx != row_idx:
                self.milestones.insert(row_idx, self.milestones.pop(old_idx))
            self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
            self.draw_chart()
            return

        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            self.tooltip = None
            
        coords = self.canvas.coords(self.drag_data["item"])
        task_idx = self.drag_data["task_idx"]
        self.milestones[task_idx]["start"] = self.start_date + timedelta(days=(coords[0] - self.chart_x) / self.pixels_per_day)
        self.milestones[task_idx]["days"] = (coords[2] - coords[0]) / self.pixels_per_day
        
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
        self.resolve_dependencies()
        self.draw_chart()

    def on_double_click(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        for tag in self.canvas.gettags(item[0]):
            if tag.startswith("task_"):
                self.open_milestone_dialog(int(tag.split("_")[1]))
                break

    def open_milestone_dialog(self, task_idx=None):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Milestone" if task_idx is not None else "Add Milestone")
        dialog.geometry(f"300x250+{self.winfo_rootx() + self.winfo_width()//2 - 150}+{self.winfo_rooty() + self.winfo_height()//2 - 125}")
        dialog.transient(self)
        dialog.grab_set() 
        
        cur_name, cur_color = "New Task", "#5da5da"
        if task_idx is not None:
            cur_name, cur_color = self.milestones[task_idx]["name"], self.milestones[task_idx]["color"]

        tk.Label(dialog, text="Milestone Name:").pack(pady=(10, 0))
        name_entry = tk.Entry(dialog, width=30)
        name_entry.insert(0, cur_name)
        name_entry.pack(pady=5)
        
        color_var = tk.StringVar(value=cur_color)
        def pick_color():
            c = colorchooser.askcolor(title="Choose color", initialcolor=color_var.get())[1]
            if c:
                color_var.set(c)
                color_btn.config(bg=c)

        tk.Label(dialog, text="Milestone Color:").pack(pady=(5, 0))
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
            if not name_entry.get().strip(): return messagebox.showwarning("Warning", "Name cannot be empty.")
            sel_idx = options.index(dep_var.get())
            dep_id = task_ids[sel_idx] if sel_idx > 0 else None
                
            if task_idx is not None:
                self.milestones[task_idx].update({"name": name_entry.get().strip(), "color": color_var.get(), "depends_on": dep_id})
            else:
                self.milestones.append({"id": str(uuid.uuid4()), "name": name_entry.get().strip(), "start": self.start_date + timedelta(days=10), "days": 30, "color": color_var.get(), "depends_on": dep_id})
            self.resolve_dependencies()
            self.draw_chart()
            dialog.destroy()

        def delete():
            if messagebox.askyesno("Confirm", "Delete this milestone?"):
                deleted_id = self.milestones[task_idx]["id"]
                del self.milestones[task_idx]
                for t in self.milestones:
                    if t.get("depends_on") == deleted_id: t["depends_on"] = None 
                self.draw_chart()
                dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Save", command=save, width=8).pack(side=tk.LEFT, padx=5)
        if task_idx is not None: tk.Button(btn_frame, text="Delete", command=delete, fg="red", width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=5)

class GanttApp(tk.Tk):
    """The main application wrapper managing tabs and session data."""
    def __init__(self):
        super().__init__()
        self.title("Advanced Project Scheduler v2.1")
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