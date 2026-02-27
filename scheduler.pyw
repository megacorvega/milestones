import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
from datetime import datetime, timedelta
import json
import os
import uuid
from PIL import ImageGrab # Requires: pip install Pillow

class GanttApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Advanced Project Scheduler v1.5")
        self.geometry("1100x600")
        
        # --- Default Dates ---
        self.start_date = datetime(2025, 1, 1)
        self.end_date = datetime(2026, 12, 30)
        
        # --- UI Setup ---
        self.setup_top_panel()
        self.setup_canvas()
        
        # --- Data Setup ---
        self.row_height = 50
        # Added UUIDs and depends_on for dependency tracking
        self.milestones = [
            {"id": str(uuid.uuid4()), "name": "8\" Design", "start": datetime(2025, 1, 1), "days": 60, "color": "#f28e2b", "depends_on": None},
            {"id": str(uuid.uuid4()), "name": "8\" Prototyping", "start": datetime(2025, 3, 5), "days": 45, "color": "#5da5da", "depends_on": None},
            {"id": str(uuid.uuid4()), "name": "8\" Testing", "start": datetime(2025, 4, 25), "days": 40, "color": "#60bd68", "depends_on": None},
            {"id": str(uuid.uuid4()), "name": "8\" Design Iteration", "start": datetime(2025, 6, 10), "days": 70, "color": "#f28e2b", "depends_on": None},
            {"id": str(uuid.uuid4()), "name": "4, 6, 10, 12 Design", "start": datetime(2025, 8, 1), "days": 250, "color": "#f28e2b", "depends_on": None}
        ]
        
        # --- Dragging State ---
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
        self.tooltip = None
        self.edge_margin = 10 
        
        self.draw_chart()

    def setup_top_panel(self):
        top_frame = tk.Frame(self, pady=10, padx=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)
        
        # Date Controls
        tk.Label(top_frame, text="Start:").pack(side=tk.LEFT)
        self.start_entry = tk.Entry(top_frame, width=10)
        self.start_entry.insert(0, self.start_date.strftime("%Y-%m-%d"))
        self.start_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(top_frame, text="End:").pack(side=tk.LEFT)
        self.end_entry = tk.Entry(top_frame, width=10)
        self.end_entry.insert(0, self.end_date.strftime("%Y-%m-%d"))
        self.end_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_frame, text="Update", command=self.update_dates).pack(side=tk.LEFT, padx=5)
        
        # Milestone Controls
        tk.Button(top_frame, text="+ Add Milestone", command=self.open_milestone_dialog, bg="#dff0d8").pack(side=tk.LEFT, padx=20)
        tk.Label(top_frame, text="(Drag labels to reorder | Double-click to edit)", fg="gray").pack(side=tk.LEFT)

        # File Controls
        tk.Button(top_frame, text="Export PNG", command=self.export_png).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Save Project", command=self.save_project).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_frame, text="Load Project", command=self.load_project).pack(side=tk.RIGHT, padx=5)

    def setup_canvas(self):
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_drag_stop)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

    # --- File Operations ---
    def get_app_dir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def save_project(self):
        file_path = filedialog.asksaveasfilename(
            initialdir=self.get_app_dir(),
            defaultextension=".projects", 
            filetypes=[("Project Files", "*.projects"), ("All Files", "*.*")]
        )
        if not file_path: return
        data = {"start_date": self.start_date.strftime("%Y-%m-%d"), "end_date": self.end_date.strftime("%Y-%m-%d"), "milestones": []}
        for task in self.milestones:
            task_copy = task.copy()
            task_copy["start"] = task["start"].strftime("%Y-%m-%d")
            data["milestones"].append(task_copy)
        try:
            with open(file_path, 'w') as f: json.dump(data, f, indent=4)
            messagebox.showinfo("Success", "Project saved successfully!")
        except Exception as e: messagebox.showerror("Error", f"Failed to save:\n{e}")

    def load_project(self):
        file_path = filedialog.askopenfilename(
            initialdir=self.get_app_dir(),
            filetypes=[("Project Files", "*.projects"), ("All Files", "*.*")]
        )
        if not file_path: return
        try:
            with open(file_path, 'r') as f: data = json.load(f)
            self.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
            self.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d")
            self.start_entry.delete(0, tk.END)
            self.start_entry.insert(0, data["start_date"])
            self.end_entry.delete(0, tk.END)
            self.end_entry.insert(0, data["end_date"])
            self.milestones = []
            for task in data["milestones"]:
                task["start"] = datetime.strptime(task["start"], "%Y-%m-%d")
                # Backwards compatibility for old save files
                if "id" not in task: task["id"] = str(uuid.uuid4())
                if "depends_on" not in task: task["depends_on"] = None
                self.milestones.append(task)
            self.resolve_dependencies()
            self.draw_chart()
        except Exception as e: messagebox.showerror("Error", f"Failed to load:\n{e}")

    def export_png(self):
        file_path = filedialog.asksaveasfilename(
            initialdir=self.get_app_dir(),
            defaultextension=".png", 
            filetypes=[("PNG Image", "*.png")]
        )
        if not file_path: return
        self.update_idletasks()
        x, y = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        x1, y1 = x + self.canvas.winfo_width(), y + self.canvas.winfo_height()
        try:
            ImageGrab.grab(bbox=(x, y, x1, y1)).save(file_path)
            messagebox.showinfo("Success", "Schedule exported as PNG!")
        except Exception as e: messagebox.showerror("Error", f"Failed to export:\n{e}")

    # --- Dependency Logic ---
    def resolve_dependencies(self):
        """Forces child milestones to start exactly when their parent ends."""
        task_map = {t["id"]: t for t in self.milestones}
        changed = True
        loops = 0
        while changed and loops < 100: # Prevent infinite loop if circular logic exists
            changed = False
            for t in self.milestones:
                if t.get("depends_on") and t["depends_on"] in task_map:
                    parent = task_map[t["depends_on"]]
                    expected_start = parent["start"] + timedelta(days=parent["days"])
                    if t["start"] != expected_start:
                        t["start"] = expected_start
                        changed = True
            loops += 1

    # --- Core Application Logic ---
    def update_dates(self):
        try:
            self.start_date = datetime.strptime(self.start_entry.get(), "%Y-%m-%d")
            self.end_date = datetime.strptime(self.end_entry.get(), "%Y-%m-%d")
            if self.end_date <= self.start_date: raise ValueError()
            self.draw_chart()
        except ValueError: messagebox.showerror("Date Error", "Please use YYYY-MM-DD format.\nEnd date must be after Start date.")

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
        
        # Grid
        num_grid_lines = 6
        for i in range(num_grid_lines + 1):
            x = self.chart_x + (self.chart_width / num_grid_lines) * i
            grid_date = self.start_date + timedelta(days=(self.total_days / num_grid_lines) * i)
            self.canvas.create_line(x, 20, x, height, fill="#e0e0e0", dash=(4, 4))
            self.canvas.create_text(x, 15, text=grid_date.strftime("%m/%d/%y"), anchor=tk.S, fill="#555")

        # Today Line
        today = datetime.now()
        if self.start_date <= today <= self.end_date:
            days_from_start = (today - self.start_date).days
            today_x = self.chart_x + (days_from_start * self.pixels_per_day)
            self.canvas.create_line(today_x, 20, today_x, height, fill="#d9534f", dash=(2, 2), width=2)
            self.canvas.create_text(today_x, height - 10, text="Today", fill="#d9534f", font=("Arial", 8, "bold"))

        # Render Tasks and Collect Coordinates for Arrows
        task_coords = {}
        y_offset = 40
        for idx, task in enumerate(self.milestones):
            self.canvas.create_text(self.label_width - 10, y_offset + self.row_height/2, text=task["name"], 
                                    anchor=tk.E, font=("Arial", 10), width=self.label_width - 20, 
                                    tags=("label", f"task_{idx}"))
            
            days_from_start = (task["start"] - self.start_date).days
            x1 = self.chart_x + (days_from_start * self.pixels_per_day)
            x2 = x1 + (task["days"] * self.pixels_per_day)
            
            # Boundary enforcements for drawing
            if x1 < self.chart_x: x1 = self.chart_x
            if x2 > self.chart_x + self.chart_width: x2 = self.chart_x + self.chart_width
            
            y1 = y_offset + 5
            y2 = y_offset + self.row_height - 5
            
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=task["color"], outline="gray", tags=("bar", f"task_{idx}"))
            
            # Save for dependency arrows
            task_coords[task["id"]] = {"x1": x1, "x2": x2, "y": y_offset + self.row_height/2}
            y_offset += self.row_height
            
        # Draw Dependency Arrows
        for task in self.milestones:
            if task.get("depends_on") and task["depends_on"] in task_coords:
                parent = task_coords[task["depends_on"]]
                child = task_coords[task["id"]]
                
                # Draw a nice angled line if needed, or straight if simple
                self.canvas.create_line(parent["x2"], parent["y"], child["x1"] - 5, child["y"], 
                                        arrow=tk.LAST, fill="#666666", width=2, smooth=True)

        self.canvas.config(scrollregion=(0, 0, width, y_offset + 50))

    # --- Interactivity ---
    def on_hover(self, event):
        item = self.canvas.find_withtag("current")
        if item and "bar" in self.canvas.gettags(item[0]):
            x1, y1, x2, y2 = self.canvas.coords(item[0])
            if abs(event.x - x1) < self.edge_margin or abs(event.x - x2) < self.edge_margin:
                self.canvas.config(cursor="sb_h_double_arrow") 
            else:
                self.canvas.config(cursor="fleur") 
        elif item and "label" in self.canvas.gettags(item[0]):
             self.canvas.config(cursor="sb_v_double_arrow") # Vertical reorder cursor
        else:
            self.canvas.config(cursor="")

    def on_drag_start(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        
        # --- Handle Vertical Reordering ---
        if "label" in tags:
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            self.drag_data = {"item": item[0], "x": event.x, "task_idx": task_idx, "mode": "reorder"}
            return

        # --- Handle Horizontal Dragging ---
        if "bar" in tags:
            x1, y1, x2, y2 = self.canvas.coords(item[0])
            mode = "move"
            if abs(event.x - x1) < self.edge_margin: mode = "resize_left"
            elif abs(event.x - x2) < self.edge_margin: mode = "resize_right"
                
            task_idx = int([t for t in tags if t.startswith("task_")][0].split("_")[1])
            
            # PREVENT DRAGGING LEFT/MOVE IF LINKED TO A PARENT
            if self.milestones[task_idx].get("depends_on"):
                if mode in ["move", "resize_left"]:
                    return # Block the action entirely
            
            self.drag_data = {"item": item[0], "x": event.x, "task_idx": task_idx, "mode": mode}

    def on_drag_motion(self, event):
        if not self.drag_data["item"]: return
            
        mode = self.drag_data["mode"]
        
        # --- Handle Vertical Reordering Visuals ---
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = int((event.y - 40) / self.row_height)
            row_idx = max(0, min(row_idx, len(self.milestones))) # Clamp
            line_y = 40 + row_idx * self.row_height
            self.canvas.create_line(10, line_y, self.chart_x + self.chart_width, line_y, 
                                    fill="blue", dash=(4, 4), tags="drop_line", width=2)
            return

        # --- Handle Horizontal Dragging Visuals ---
        item = self.drag_data["item"]
        delta_x = event.x - self.drag_data["x"]
        
        x1, y1, x2, y2 = self.canvas.coords(item)
        min_x = self.chart_x
        max_x = self.chart_x + self.chart_width
        min_width = 5 
        
        if mode == "move":
            if x1 + delta_x < min_x: delta_x = min_x - x1
            elif x2 + delta_x > max_x: delta_x = max_x - x2
            self.canvas.move(item, delta_x, 0)
            self.drag_data["x"] += delta_x
            
        elif mode == "resize_left":
            new_x1 = x1 + delta_x
            if new_x1 < min_x: new_x1 = min_x
            if new_x1 > x2 - min_width: new_x1 = x2 - min_width
            self.canvas.coords(item, new_x1, y1, x2, y2)
            self.drag_data["x"] = new_x1
            
        elif mode == "resize_right":
            new_x2 = x2 + delta_x
            if new_x2 > max_x: new_x2 = max_x
            if new_x2 < x1 + min_width: new_x2 = x1 + min_width
            self.canvas.coords(item, x1, y1, new_x2, y2)
            self.drag_data["x"] = new_x2

        coords = self.canvas.coords(item)
        days_from_start = (coords[0] - self.chart_x) / self.pixels_per_day
        new_start = self.start_date + timedelta(days=days_from_start)
        task_days = (coords[2] - coords[0]) / self.pixels_per_day
        new_end = new_start + timedelta(days=task_days)
        
        tooltip_text = f"Start: {new_start.strftime('%m/%d/%y')} | End: {new_end.strftime('%m/%d/%y')} | Days: {int(task_days)}"
        
        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            
        text_id = self.canvas.create_text(event.x, coords[1] - 15, text=tooltip_text, font=("Arial", 9, "bold"), fill="black")
        bbox = self.canvas.bbox(text_id)
        rect_id = self.canvas.create_rectangle(bbox[0]-5, bbox[1]-2, bbox[2]+5, bbox[3]+2, fill="#ffffcc", outline="black")
        self.canvas.tag_raise(text_id)
        self.tooltip = {"text": text_id, "rect": rect_id}

    def on_drag_stop(self, event):
        if not self.drag_data["item"]: return
            
        mode = self.drag_data["mode"]
        
        # --- Handle Vertical Reordering Apply ---
        if mode == "reorder":
            self.canvas.delete("drop_line")
            row_idx = int((event.y - 40) / self.row_height)
            row_idx = max(0, min(row_idx, len(self.milestones)))
            
            old_idx = self.drag_data["task_idx"]
            if row_idx > old_idx:
                row_idx -= 1 # Adjust for shifting elements
                
            if old_idx != row_idx:
                task = self.milestones.pop(old_idx)
                self.milestones.insert(row_idx, task)
            
            self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
            self.draw_chart()
            return

        # --- Handle Horizontal Apply ---
        if self.tooltip:
            self.canvas.delete(self.tooltip["rect"])
            self.canvas.delete(self.tooltip["text"])
            self.tooltip = None
            
        coords = self.canvas.coords(self.drag_data["item"])
        days_from_start = (coords[0] - self.chart_x) / self.pixels_per_day
        task_days = (coords[2] - coords[0]) / self.pixels_per_day
        
        task_idx = self.drag_data["task_idx"]
        self.milestones[task_idx]["start"] = self.start_date + timedelta(days=days_from_start)
        self.milestones[task_idx]["days"] = task_days
        
        self.drag_data = {"item": None, "x": 0, "task_idx": None, "mode": None}
        
        # Recalculate any children that depend on the changed task
        self.resolve_dependencies()
        self.draw_chart()

    # --- CRUD Operations ---
    def on_double_click(self, event):
        item = self.canvas.find_withtag("current")
        if not item: return
        tags = self.canvas.gettags(item[0])
        for tag in tags:
            if tag.startswith("task_"):
                task_idx = int(tag.split("_")[1])
                self.open_milestone_dialog(task_idx)
                break

    def open_milestone_dialog(self, task_idx=None):
        dialog = tk.Toplevel(self)
        dialog.title("Edit Milestone" if task_idx is not None else "Add Milestone")
        
        dialog_width = 300
        dialog_height = 250 # Increased slightly for dependency dropdown
        
        self.update_idletasks()
        parent_x, parent_y = self.winfo_rootx(), self.winfo_rooty()
        parent_width, parent_height = self.winfo_width(), self.winfo_height()
        pos_x = parent_x + (parent_width // 2) - (dialog_width // 2)
        pos_y = parent_y + (parent_height // 2) - (dialog_height // 2)
        
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        dialog.transient(self)
        dialog.grab_set() 
        
        # Data prep
        current_name = "New Task"
        current_color = "#5da5da"
        if task_idx is not None:
            current_name = self.milestones[task_idx]["name"]
            current_color = self.milestones[task_idx]["color"]

        # Form Elements
        tk.Label(dialog, text="Milestone Name:").pack(pady=(10, 0))
        name_entry = tk.Entry(dialog, width=30)
        name_entry.insert(0, current_name)
        name_entry.pack(pady=5)
        
        color_var = tk.StringVar(value=current_color)
        def pick_color():
            color_code = colorchooser.askcolor(title="Choose color", initialcolor=color_var.get())[1]
            if color_code:
                color_var.set(color_code)
                color_btn.config(bg=color_code)

        tk.Label(dialog, text="Milestone Color:").pack(pady=(5, 0))
        color_btn = tk.Button(dialog, text="Pick Color", command=pick_color, bg=current_color, width=15)
        color_btn.pack(pady=5)
        
        # --- Dependency Dropdown Setup ---
        tk.Label(dialog, text="Depends On (Starts after):").pack(pady=(5, 0))
        dep_var = tk.StringVar()
        options = ["None"]
        task_ids = [""]
        
        for i, t in enumerate(self.milestones):
            if i != task_idx: # Prevent linking to itself
                options.append(t["name"])
                task_ids.append(t["id"])
                
        dep_combo = ttk.Combobox(dialog, textvariable=dep_var, values=options, state="readonly")
        
        current_dep = "None"
        if task_idx is not None and self.milestones[task_idx].get("depends_on"):
            dep_id = self.milestones[task_idx]["depends_on"]
            if dep_id in task_ids:
                current_dep = options[task_ids.index(dep_id)]
        
        dep_combo.set(current_dep)
        dep_combo.pack(pady=5)
        # ---------------------------------
        
        def save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Name cannot be empty.")
                return
                
            # Grab selected dependency ID
            sel_idx = options.index(dep_var.get())
            selected_dep_id = task_ids[sel_idx] if sel_idx > 0 else None
                
            if task_idx is not None:
                self.milestones[task_idx]["name"] = name
                self.milestones[task_idx]["color"] = color_var.get()
                self.milestones[task_idx]["depends_on"] = selected_dep_id
            else:
                self.milestones.append({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "start": self.start_date + timedelta(days=10),
                    "days": 30,
                    "color": color_var.get(),
                    "depends_on": selected_dep_id
                })
            
            self.resolve_dependencies()
            self.draw_chart()
            dialog.destroy()

        def delete():
            if messagebox.askyesno("Confirm", "Delete this milestone?"):
                # Clean up dependencies if anything relied on this deleted task
                deleted_id = self.milestones[task_idx]["id"]
                del self.milestones[task_idx]
                for t in self.milestones:
                    if t.get("depends_on") == deleted_id:
                        t["depends_on"] = None 
                        
                self.draw_chart()
                dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Save", command=save, width=8).pack(side=tk.LEFT, padx=5)
        if task_idx is not None:
            tk.Button(btn_frame, text="Delete", command=delete, fg="red", width=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=5)

if __name__ == "__main__":
    app = GanttApp()
    app.mainloop()