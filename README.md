# Milestones

A lightweight, standalone Python application for creating and managing visual project schedules (Gantt charts). Built with Python's `tkinter` library, it offers a highly interactive drag-and-drop interface, task dependencies, and automated export tools without the bloat of traditional enterprise project management software.

## ✨ Features

* **Interactive Visual Workspace:** * **Drag & Drop:** Click and drag milestones horizontally to change their dates.
    * **Resize:** Hover over the left or right edge of a milestone to resize its duration.
    * **Reorder:** Drag task labels vertically to reorganize your project flow.
* **Smart Dependencies:** Link tasks together. Child tasks automatically snap to the end date of their parent, visualized by clean, orthogonal routing arrows.
* **Tabbed Interface:** Work on multiple `.projects` files simultaneously. The app features session management to remember and automatically reload your open tabs the next time you launch it.
* **Real-time Tooltips:** See exact start dates, end dates, and total durations overlaid on the screen as you interact with tasks.
* **Automated Exporting & Logging:** * Export your current schedule to a `.png` file that automatically crops out empty whitespace.
    * Auto-archives previous image exports to prevent overwriting.
    * Automatically generates and appends to a `.changelog` text file, documenting the exact start and end dates of all milestones at the time of export.
* **Customization:** Double-click any task to rename it, change its color using a built-in color picker, or update its dependencies.

## 🚀 Installation & Setup

1.  **Prerequisites:** You must have Python installed. 
2.  **Dependencies:** This application relies heavily on Python's built-in libraries (like `tkinter` and `json`), but it requires the `Pillow` library to capture screen data for image exports.
    ```bash
    pip install Pillow
    ```
3.  **Running the App:** Simply run the script from your terminal:
    ```bash
    python scheduler.pyw
    ```
    *(Note: On Windows, you can also just double-click the `scheduler.pyw` file to run it natively without a command prompt window appearing).*

## 📂 File Types

This application generates and interacts with a few specific files in its root directory:

* `*.projects`: The native save file format (standard JSON) containing your milestone data, dates, and colors.
* `session.json`: A hidden memory file that tracks which tabs you have open so you don't lose your workspace layout between sessions.
* `*.png`: The auto-cropped image export of your schedule.
* `*.changelog`: A running text log that documents your project dates every time you trigger an export.
* `/archive`: A folder automatically generated to store older versions of your PNG exports.

## 🛠️ Usage Tips

* **Boundary Enforcement:** Tasks linked as dependencies cannot be manually dragged to a date prior to their parent's completion. 
* **"Today" Marker:** A red dashed line will automatically render on the chart to indicate the current date relative to your project timeline.
* **Responsive Resizing:** The chart automatically recalculates and redraws itself if you resize the main application window.

---
*Built with Python & Tkinter.*
