"""Tkinter entry point for the local Windows desktop application."""

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from src.app_logic import (AppSettings, DisplayStatus, ProcessOutcome, SettingsStore,
                           approve_and_save, discover_pdfs, process_one)
from src.config import APP_DIR_NAME, APP_NAME, APP_VERSION
from src.excel import ExcelRegister
from src.models import DocumentResult
from src.ocr import TesseractOCR
from src.pdf import render_first_page
from src.preview import fit_preview


log = logging.getLogger(__name__)


class ReviewWindow:
    def __init__(self, app: "DocumentRegisterApp", pdf_path: Path, result: DocumentResult):
        self.app = app
        self.review_paths = [path for path in app.paths
                             if app.outcomes[path].status == DisplayStatus.NEEDS_REVIEW]
        self.index = self.review_paths.index(pdf_path)
        self.drafts: dict[Path, tuple[str, str, str, str, str]] = {}
        self._source_image = None
        self._photo = None
        self._resize_job = None
        self.window = tk.Toplevel(app.root)
        self.window.geometry("1120x760")
        self.window.minsize(860, 580)
        self.window.transient(app.root)
        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Review document", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.file_label = ttk.Label(outer, text="", wraplength=950)
        self.file_label.pack(anchor="w", pady=(3, 12))

        panes = ttk.PanedWindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.panes = panes
        preview_frame = ttk.LabelFrame(panes, text="PDF page 1", padding=8)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        preview_tools = ttk.Frame(preview_frame)
        preview_tools.grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Button(preview_tools, text="Zoom In", command=self.zoom_in).pack(side="left")
        ttk.Button(preview_tools, text="Fit Page", command=self.fit_page).pack(side="left", padx=(6, 0))
        self.preview_canvas = tk.Canvas(preview_frame, background="white", highlightthickness=1,
                                        highlightbackground="#c7c7c7")
        self.preview_canvas.grid(row=1, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._schedule_preview_resize)
        vertical_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_canvas.yview)
        vertical_scroll.grid(row=1, column=1, sticky="ns")
        horizontal_scroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview_canvas.xview)
        horizontal_scroll.grid(row=2, column=0, sticky="ew")
        self.preview_canvas.configure(xscrollcommand=horizontal_scroll.set, yscrollcommand=vertical_scroll.set)
        self._zoom = 1.0
        panes.add(preview_frame, weight=3)

        fields = ttk.LabelFrame(panes, text="Extracted information", padding=18)
        fields.columnconfigure(0, weight=1)
        fields.rowconfigure(7, weight=1)
        self.origin_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.receipt_var = tk.StringVar()
        ttk.Label(fields, text="Origin").grid(row=0, column=0, sticky="w")
        ttk.Entry(fields, textvariable=self.origin_var).grid(row=1, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(fields, text="To").grid(row=2, column=0, sticky="w")
        ttk.Entry(fields, textvariable=self.to_var).grid(row=3, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(fields, text="From").grid(row=4, column=0, sticky="w")
        ttk.Entry(fields, textvariable=self.from_var).grid(row=5, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(fields, text="Subject").grid(row=6, column=0, sticky="w")
        self.subject_text = tk.Text(fields, width=34, height=6, wrap="word", font=("Segoe UI", 10))
        self.subject_text.grid(row=7, column=0, sticky="nsew", pady=(4, 10))
        ttk.Label(fields, text="Receipt Date (DD-Mon-YYYY)").grid(row=8, column=0, sticky="w")
        ttk.Entry(fields, textvariable=self.receipt_var).grid(row=9, column=0, sticky="ew", pady=(4, 10))
        ttk.Label(fields, text="Review notes").grid(row=10, column=0, sticky="w")
        self.warnings_label = ttk.Label(fields, text="", wraplength=350, justify="left")
        self.warnings_label.grid(row=11, column=0, sticky="nw", pady=(4, 0))
        panes.add(fields, weight=2)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        self.footer = footer
        self.previous_button = ttk.Button(footer, text="Previous", command=lambda: self.navigate(-1))
        self.previous_button.pack(side="left")
        self.position_label = ttk.Label(footer, text="")
        self.position_label.pack(side="left", padx=12)
        self.next_button = ttk.Button(footer, text="Next", command=lambda: self.navigate(1))
        self.next_button.pack(side="left")
        ttk.Button(footer, text="Approve & Save", command=self.approve).pack(side="right")
        ttk.Button(footer, text="Close", command=self.window.destroy).pack(side="right", padx=(0, 8))
        ttk.Button(footer, text="Open PDF", command=self.open_pdf).pack(side="right", padx=(0, 8))
        self._load_current()
        self.window.after(80, self._set_initial_split)
        self.window.grab_set()

    def _set_initial_split(self):
        if self.window.winfo_exists() and self.panes.winfo_width() > 100:
            self.panes.sashpos(0, round(self.panes.winfo_width() * 0.55))
            self._schedule_preview_resize()

    def _save_draft(self):
        self.drafts[self.pdf_path] = (self.origin_var.get(), self.to_var.get(), self.from_var.get(),
                                      self.subject_text.get("1.0", "end-1c"), self.receipt_var.get())

    def _load_current(self):
        self.pdf_path = self.review_paths[self.index]
        result = self.app.outcomes[self.pdf_path].result
        values = self.drafts.get(self.pdf_path, (result.origin, result.to, result.from_, result.subject,
                                                 result.receipt_date.strftime("%d-%b-%Y") if result.receipt_date else ""))
        self.origin_var.set(values[0])
        self.to_var.set(values[1])
        self.from_var.set(values[2])
        self.subject_text.delete("1.0", "end")
        self.subject_text.insert("1.0", values[3])
        self.receipt_var.set(values[4])
        self.file_label.configure(text=self.pdf_path.name)
        self.window.title(f"Review — {self.pdf_path.name}")
        self.position_label.configure(text=f"{self.index + 1} of {len(self.review_paths)}")
        self.previous_button.configure(state="normal" if self.index > 0 else "disabled")
        self.next_button.configure(state="normal" if self.index < len(self.review_paths) - 1 else "disabled")
        notes = "\n".join("• " + warning for warning in result.warnings) or "Please verify the fields against the PDF."
        self.warnings_label.configure(text=notes)
        self._photo = None
        self._source_image = None
        self._zoom = 1.0
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(20, 20, text="Loading preview…", anchor="nw")
        try:
            self._source_image = render_first_page(self.pdf_path, dpi=120)
        except Exception:
            log.exception("Could not render preview for %s", self.pdf_path.name)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(20, 20, text="Preview unavailable. Use Open PDF to inspect the document.",
                                            anchor="nw", width=300)
            return
        self.window.update_idletasks()
        self._fit_preview()

    def _schedule_preview_resize(self, _event=None):
        if self._resize_job:
            self.window.after_cancel(self._resize_job)
        self._resize_job = self.window.after(120, self._fit_preview)

    def _fit_preview(self):
        self._resize_job = None
        if self._source_image is None or not self.preview_canvas.winfo_exists():
            return
        bounds = (self.preview_canvas.winfo_width() - 8, self.preview_canvas.winfo_height() - 8)
        if min(bounds) < 50:
            return
        base = fit_preview(self._source_image, bounds)
        fitted = base if self._zoom == 1.0 else self._source_image.resize(
            (round(base.width * self._zoom), round(base.height * self._zoom)), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(fitted, master=self.window)
        canvas_width, canvas_height = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        x = max(0, (canvas_width - fitted.width) // 2)
        y = max(0, (canvas_height - fitted.height) // 2)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(x, y, image=self._photo, anchor="nw")
        self.preview_canvas.configure(scrollregion=(0, 0, max(canvas_width, fitted.width),
                                                    max(canvas_height, fitted.height)))

    def zoom_in(self):
        self._zoom = min(2.5, self._zoom * 1.5)
        self._fit_preview()

    def fit_page(self):
        self._zoom = 1.0
        self._fit_preview()

    def navigate(self, delta: int):
        target = self.index + delta
        if not 0 <= target < len(self.review_paths):
            return
        self._save_draft()
        self.index = target
        self._load_current()

    def open_pdf(self):
        try:
            os.startfile(self.pdf_path)  # Windows default PDF viewer
        except OSError:
            log.exception("Could not open PDF %s", self.pdf_path.name)
            messagebox.showerror(APP_NAME, "Unable to open the selected PDF.", parent=self.window)

    def approve(self):
        try:
            created = approve_and_save(self.pdf_path, self.app.register,
                                       self.to_var.get(), self.from_var.get(),
                                       self.subject_text.get("1.0", "end-1c"),
                                       self.origin_var.get(), self.receipt_var.get())
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc), parent=self.window)
            return
        except Exception:
            log.exception("Approval could not be saved for %s", self.pdf_path.name)
            messagebox.showerror(APP_NAME, "Unable to write to the Excel register. Close it in Excel and try again.", parent=self.window)
            return
        self.app.update_document(self.pdf_path, ProcessOutcome(
            DisplayStatus.PROCESSED if created else DisplayStatus.ALREADY_PROCESSED))
        self.drafts.pop(self.pdf_path, None)
        self.review_paths.pop(self.index)
        if self.review_paths:
            self.index = min(self.index, len(self.review_paths) - 1)
            self._load_current()
        else:
            self.window.destroy()


class DocumentRegisterApp:
    def __init__(self, root: tk.Tk, settings_store: SettingsStore | None = None):
        self.root = root
        self._show_first_run = settings_store is None
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.folder: Path | None = None
        self.register: ExcelRegister | None = None
        self.paths: list[Path] = []
        self.outcomes: dict[Path, ProcessOutcome] = {}
        self._events: queue.Queue = queue.Queue()
        self._busy = False
        self._completed = 0
        self._total = 0
        self._build_ui()
        self._restore_settings()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        if self._show_first_run and self.register is None:
            self.root.after(350, self._first_run_register_prompt)

    def _build_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry("900x620")
        self.root.minsize(720, 520)
        self.root.option_add("*Font", "{Segoe UI} 10")
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)
        ttk.Label(outer, text=APP_NAME, font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 18))

        folder_frame = ttk.LabelFrame(outer, text="Document folder", padding=12)
        folder_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        folder_frame.columnconfigure(0, weight=1)
        self.folder_label = ttk.Label(folder_frame, text="No folder selected", wraplength=650)
        self.folder_label.grid(row=0, column=0, sticky="w")
        self.folder_button = ttk.Button(folder_frame, text="Select Folder", command=self.select_folder)
        self.folder_button.grid(row=0, column=1, padx=(12, 0))
        self.count_label = ttk.Label(folder_frame, text="0 PDF documents found")
        self.count_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        register_frame = ttk.LabelFrame(outer, text="Excel register", padding=12)
        register_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        register_frame.columnconfigure(0, weight=1)
        self.register_label = ttk.Label(register_frame, text="No register selected", wraplength=520)
        self.register_label.grid(row=0, column=0, sticky="w")
        self.register_button = ttk.Button(register_frame, text="Choose Existing", command=self.choose_register)
        self.register_button.grid(row=0, column=1, padx=(12, 0))
        self.create_button = ttk.Button(register_frame, text="Create New", command=self.create_register)
        self.create_button.grid(row=0, column=2, padx=(8, 0))
        self.open_register_button = ttk.Button(register_frame, text="Open Register", command=self.open_register)
        self.open_register_button.grid(row=1, column=1, columnspan=2, sticky="e", pady=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        actions.columnconfigure(1, weight=1)
        self.process_button = ttk.Button(actions, text="Process Documents", command=self.process_documents)
        self.process_button.grid(row=0, column=0)
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(18, 10))
        self.progress_label = ttk.Label(actions, text="0 / 0")
        self.progress_label.grid(row=0, column=2)
        self.activity_label = ttk.Label(outer, text="Select a folder and an Excel register to begin.")
        self.activity_label.grid(row=4, column=0, sticky="w", pady=(0, 12))

        documents = ttk.LabelFrame(outer, text="Documents", padding=10)
        documents.grid(row=5, column=0, sticky="nsew")
        documents.columnconfigure(0, weight=1)
        documents.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(documents, columns=("file", "status"), show="headings", selectmode="browse")
        self.tree.heading("file", text="File")
        self.tree.heading("status", text="Status")
        self.tree.column("file", width=590, stretch=True)
        self.tree.column("status", width=170, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(documents, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _event: self.review_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._on_selection())
        bottom = ttk.Frame(outer)
        bottom.grid(row=6, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        self.summary_label = ttk.Label(bottom, text="Processed: 0    Needs Review: 0    Already Processed: 0    Failed: 0")
        self.summary_label.grid(row=0, column=0, sticky="w")
        self.review_button = ttk.Button(bottom, text="Review Selected", command=self.review_selected)
        self.review_button.grid(row=0, column=1)
        self.open_pdf_button = ttk.Button(bottom, text="Open PDF", command=self.open_selected_pdf)
        self.open_pdf_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Button(bottom, text="About", command=self.show_about).grid(row=0, column=3, padx=(8, 0))
        self._update_buttons()

    def _first_run_register_prompt(self):
        if self.register is not None or not self.root.winfo_exists():
            return
        prompt = tk.Toplevel(self.root)
        prompt.title("Choose an Excel register")
        prompt.resizable(False, False)
        prompt.transient(self.root)
        frame = ttk.Frame(prompt, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Set up your Excel register", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Choose an existing register or create a new one to begin processing PDFs.",
                  wraplength=430).pack(anchor="w", pady=(8, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")

        def choose(action):
            prompt.destroy()
            action()

        ttk.Button(buttons, text="Later", command=prompt.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Choose Existing", command=lambda: choose(self.choose_register)).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Create New", command=lambda: choose(self.create_register)).pack(side="left")
        prompt.grab_set()

    def show_about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME}\nVersion {APP_VERSION}\n\nProcesses scanned correspondence locally.",
                            parent=self.root)

    def _restore_settings(self):
        if self.settings.register_path:
            path = Path(self.settings.register_path)
            if path.is_file():
                try:
                    register = ExcelRegister(path)
                    register.validate()
                    register.migrate()
                    self.register = register
                    self.register_label.configure(text=str(path))
                except Exception:
                    log.exception("Saved register is unavailable")
                    self.activity_label.configure(text="The previous Excel register could not be opened. Choose another register.")
            else:
                self.activity_label.configure(text="The previous Excel register was not found. Choose a register.")
        if self.settings.document_folder:
            folder = Path(self.settings.document_folder)
            if folder.is_dir():
                self.set_folder(folder, remember=False)
            else:
                self.activity_label.configure(text="The previous document folder was not found. Select a folder.")
        self._update_buttons()

    def _remember(self):
        self.settings.document_folder = str(self.folder) if self.folder else ""
        self.settings.register_path = str(self.register.path) if self.register else ""
        try:
            self.settings_store.save(self.settings)
        except OSError:
            log.exception("Could not save settings")
            self.activity_label.configure(text="Preferences could not be saved; the current selection still works.")

    def select_folder(self):
        chosen = filedialog.askdirectory(parent=self.root, title="Select a folder containing PDFs",
                                         initialdir=str(self.folder or Path.home()))
        if chosen:
            self.set_folder(Path(chosen))

    def set_folder(self, folder: Path, remember: bool = True):
        if self._busy:
            return
        try:
            if not folder.is_dir():
                raise FileNotFoundError(folder)
            paths = discover_pdfs(folder)
        except OSError:
            log.exception("Could not read selected folder")
            messagebox.showerror(APP_NAME, "Unable to open the selected folder.", parent=self.root)
            return
        self.folder = folder
        self.paths = paths
        self.outcomes = {path: ProcessOutcome(DisplayStatus.READY) for path in paths}
        for row in self.tree.get_children():
            self.tree.delete(row)
        for index, path in enumerate(paths):
            self.tree.insert("", "end", iid=str(index), values=(path.name, DisplayStatus.READY.value))
        self.folder_label.configure(text=str(folder))
        self.count_label.configure(text=f"{len(paths)} PDF document{'s' if len(paths) != 1 else ''} found")
        self.activity_label.configure(text="Ready to process." if paths else "No PDF files found directly in this folder.")
        self.progress.configure(value=0, maximum=max(len(paths), 1))
        self.progress_label.configure(text=f"0 / {len(paths)}")
        self._update_summary()
        self._update_buttons()
        if remember:
            self._remember()

    def choose_register(self):
        chosen = filedialog.askopenfilename(parent=self.root, title="Choose Excel register",
                                            filetypes=[("Excel workbooks", "*.xlsx")])
        if chosen:
            self.set_register(Path(chosen))

    def create_register(self):
        chosen = filedialog.asksaveasfilename(parent=self.root, title="Create Excel register",
                                              defaultextension=".xlsx", filetypes=[("Excel workbooks", "*.xlsx")])
        if chosen:
            self.set_register(Path(chosen), create=True)

    def set_register(self, path: Path, create: bool = False):
        if self._busy:
            return
        if path.suffix.lower() != ".xlsx":
            messagebox.showerror(APP_NAME, "Select an Excel .xlsx file.", parent=self.root)
            return
        candidate = ExcelRegister(path)
        try:
            if create:
                candidate.create()
            else:
                candidate.validate()
                candidate.migrate()
        except FileExistsError:
            messagebox.showerror(APP_NAME, "That file already exists. Choose a new file name or select it as an existing register.", parent=self.root)
            return
        except Exception:
            log.exception("Could not select register")
            messagebox.showerror(APP_NAME, "Unable to open this Excel register. Check that it is a valid register and is not open in Excel.", parent=self.root)
            return
        self.register = candidate
        self.register_label.configure(text=str(path))
        if self.folder:
            self.set_folder(self.folder, remember=False)
        self._remember()
        self._update_buttons()

    def open_register(self):
        if not self.register:
            return
        try:
            os.startfile(self.register.path)
        except OSError:
            log.exception("Could not open register")
            messagebox.showerror(APP_NAME, "Unable to open the Excel register.", parent=self.root)

    def process_documents(self):
        if self._busy or not self.register:
            return
        pending = [path for path in self.paths if self.outcomes[path].status in (DisplayStatus.READY, DisplayStatus.FAILED)]
        if not pending:
            self.activity_label.configure(text="No new documents to process. Select a Needs Review row to approve it.")
            return
        self._busy = True
        self._completed = 0
        self._total = len(pending)
        self.progress.configure(value=0, maximum=self._total)
        self.progress_label.configure(text=f"0 / {self._total}")
        self._update_buttons()
        register = self.register

        def work():
            try:
                ocr = TesseractOCR()
                for index, path in enumerate(pending, 1):
                    self._events.put(("start", path, index))
                    outcome = process_one(path, register, ocr)
                    self._events.put(("done", path, outcome))
            except Exception:
                log.exception("Unexpected batch processing failure")
                self._events.put(("batch_error",))
            finally:
                self._events.put(("finished",))

        threading.Thread(target=work, daemon=True, name="document-processing").start()
        self.root.after(100, self._drain_events)

    def _drain_events(self):
        try:
            while True:
                event = self._events.get_nowait()
                if event[0] == "start":
                    _, path, index = event
                    self.update_document(path, ProcessOutcome(DisplayStatus.PROCESSING))
                    self.activity_label.configure(text=f"Processing {path.name} ({index} / {self._total})")
                elif event[0] == "done":
                    _, path, outcome = event
                    self.update_document(path, outcome)
                    self._completed += 1
                    self.progress.configure(value=self._completed)
                    self.progress_label.configure(text=f"{self._completed} / {self._total}")
                elif event[0] == "batch_error":
                    self.activity_label.configure(text="Processing stopped unexpectedly. Check the application log.")
                elif event[0] == "finished":
                    self._busy = False
                    if self._completed == self._total:
                        self.activity_label.configure(text="Processing complete. Review any documents marked Needs Review.")
                    self._update_buttons()
        except queue.Empty:
            pass
        if self._busy:
            self.root.after(100, self._drain_events)

    def update_document(self, path: Path, outcome: ProcessOutcome):
        self.outcomes[path] = outcome
        row = str(self.paths.index(path))
        self.tree.item(row, values=(path.name, outcome.status.value))
        self._update_summary()
        self._update_buttons()

    def _update_summary(self):
        counts = {status: sum(item.status == status for item in self.outcomes.values()) for status in DisplayStatus}
        self.summary_label.configure(text=(
            f"Processed: {counts[DisplayStatus.PROCESSED]}    "
            f"Needs Review: {counts[DisplayStatus.NEEDS_REVIEW]}    "
            f"Already Processed: {counts[DisplayStatus.ALREADY_PROCESSED]}    "
            f"Failed: {counts[DisplayStatus.FAILED]}"))

    def _selected_path(self) -> Path | None:
        selection = self.tree.selection()
        return self.paths[int(selection[0])] if selection else None

    def _on_selection(self):
        if self._busy:
            self._update_buttons()
            return
        path = self._selected_path()
        if path:
            outcome = self.outcomes[path]
            if outcome.message:
                self.activity_label.configure(text=outcome.message)
            elif outcome.status == DisplayStatus.NEEDS_REVIEW:
                self.activity_label.configure(text="Select Review Selected to check and correct this document.")
        self._update_buttons()

    def _update_buttons(self):
        self.folder_button.configure(state="disabled" if self._busy else "normal")
        self.register_button.configure(state="disabled" if self._busy else "normal")
        self.create_button.configure(state="disabled" if self._busy else "normal")
        self.process_button.configure(state="normal" if not self._busy and self.register and self.paths else "disabled")
        self.open_register_button.configure(state="normal" if self.register and not self._busy else "disabled")
        selected = self._selected_path()
        self.open_pdf_button.configure(state="normal" if selected is not None else "disabled")
        can_review = (not self._busy and selected is not None and
                      self.outcomes[selected].status == DisplayStatus.NEEDS_REVIEW)
        self.review_button.configure(state="normal" if can_review else "disabled")

    def review_selected(self):
        path = self._selected_path()
        if self._busy or path is None:
            return None
        outcome = self.outcomes[path]
        if outcome.status != DisplayStatus.NEEDS_REVIEW or not outcome.result:
            return None
        return ReviewWindow(self, path, outcome.result)

    def open_selected_pdf(self):
        path = self._selected_path()
        if not path:
            return
        try:
            os.startfile(path)
        except OSError:
            log.exception("Could not open PDF %s", path.name)
            messagebox.showerror(APP_NAME, "Unable to open the selected PDF.", parent=self.root)

    def _close(self):
        if self._busy:
            messagebox.showinfo(APP_NAME, "Documents are still being processed. Please wait until processing finishes.", parent=self.root)
            return
        self.root.destroy()


def configure_logging():
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / ".local" / "share") / APP_DIR_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=base / "document-register.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except OSError:
        logging.basicConfig(level=logging.INFO)


def main():
    configure_logging()
    root = tk.Tk()
    DocumentRegisterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
