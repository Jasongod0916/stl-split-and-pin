from __future__ import annotations

import json
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from split_stl import split_file


DEFAULT_INPUT = Path(r"C:\A1Mini_STL_Splitter\test.stl")


class SplitterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("STL Splitter")
        self.geometry("760x520")
        self.minsize(680, 460)

        default_input = DEFAULT_INPUT if DEFAULT_INPUT.exists() else Path()
        default_output = (
            default_input.with_name(f"{default_input.stem}_split")
            if default_input
            else Path.cwd() / "output"
        )

        self.input_path = tk.StringVar(value=str(default_input) if default_input else "")
        self.output_dir = tk.StringVar(value=str(default_output))
        self.axis = tk.StringVar(value="y" if default_input else "auto")
        self.position = tk.StringVar()
        self.pins = tk.IntVar(value=0)
        self.pin_radius = tk.DoubleVar(value=3.0)
        self.pin_length = tk.DoubleVar(value=12.0)
        self.socket_holes = tk.BooleanVar(value=False)
        self.rotate_z = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="Ready to split." if default_input else "Select an STL file to begin.")

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=18)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="STL file").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(main, textvariable=self.input_path).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(main, text="Browse...", command=self.choose_input).grid(row=0, column=2, sticky="ew")

        ttk.Label(main, text="Output folder").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(main, textvariable=self.output_dir).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(main, text="Browse...", command=self.choose_output).grid(row=1, column=2, sticky="ew")

        settings = ttk.LabelFrame(main, text="Split settings", padding=12)
        settings.grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)
        for col in range(6):
            settings.columnconfigure(col, weight=1)

        ttk.Label(settings, text="Axis").grid(row=0, column=0, sticky="w")
        axis_box = ttk.Combobox(settings, textvariable=self.axis, values=("auto", "x", "y", "z"), state="readonly", width=8)
        axis_box.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 8))

        ttk.Label(settings, text="Position (blank=center)").grid(row=0, column=1, sticky="w")
        ttk.Entry(settings, textvariable=self.position, width=16).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 8))

        ttk.Label(settings, text="Pins").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(settings, textvariable=self.pins, from_=0, to=12, width=8).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(2, 8))

        ttk.Label(settings, text="Pin radius mm").grid(row=0, column=3, sticky="w")
        ttk.Spinbox(settings, textvariable=self.pin_radius, from_=1.0, to=20.0, increment=0.5, width=10).grid(row=1, column=3, sticky="ew", padx=(0, 8), pady=(2, 8))

        ttk.Label(settings, text="Pin length mm").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(settings, textvariable=self.pin_length, from_=4.0, to=80.0, increment=1.0, width=10).grid(row=1, column=4, sticky="ew", padx=(0, 8), pady=(2, 8))

        ttk.Label(settings, text="Build volume").grid(row=0, column=5, sticky="w")
        ttk.Label(settings, text="180 x 180 x 180 mm").grid(row=1, column=5, sticky="w", pady=(2, 8))

        ttk.Label(settings, text="Rotate Z before split").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Spinbox(settings, textvariable=self.rotate_z, from_=0.0, to=359.0, increment=1.0, width=8).grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(4, 0))
        ttk.Checkbutton(settings, text="Cut socket holes", variable=self.socket_holes).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(settings, text="Mode").grid(row=2, column=4, sticky="e", padx=(0, 8), pady=(4, 0))
        ttk.Label(settings, text="One cut, two parts").grid(row=2, column=5, sticky="w", pady=(4, 0))

        controls = ttk.Frame(main)
        controls.grid(row=3, column=0, columnspan=3, sticky="ew")
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.split_button = ttk.Button(controls, text="Split STL", command=self.start_split)
        self.split_button.grid(row=0, column=1, sticky="e")

        self.output_text = tk.Text(main, height=14, wrap="word")
        self.output_text.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        main.rowconfigure(4, weight=1)

    def choose_input(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose STL file",
            filetypes=(("STL files", "*.stl"), ("All files", "*.*")),
        )
        if not filename:
            return
        self.input_path.set(filename)
        path = Path(filename)
        self.output_dir.set(str(path.with_name(f"{path.stem}_split")))
        self.status.set("Ready to split.")

    def choose_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir.set(folder)

    def start_split(self) -> None:
        try:
            input_path = Path(self.input_path.get())
            out_dir = Path(self.output_dir.get())
            if not input_path.exists():
                raise ValueError("Please choose an existing STL file.")
            position = float(self.position.get()) if self.position.get().strip() else None
        except Exception as exc:
            messagebox.showerror("Cannot start", str(exc))
            return

        self.split_button.configure(state=tk.DISABLED)
        self.status.set("Splitting STL...")
        self.output_text.delete("1.0", tk.END)

        worker = threading.Thread(
            target=self._run_split,
            args=(input_path, out_dir, position),
            daemon=True,
        )
        worker.start()

    def _run_split(self, input_path: Path, out_dir: Path, position: float | None) -> None:
        try:
            report = split_file(
                input_path=input_path,
                out_dir=out_dir,
                axis_name=self.axis.get(),
                position=position,
                build_volume=(180.0, 180.0, 180.0),
                pins=int(self.pins.get()),
                pin_radius=float(self.pin_radius.get()),
                pin_length=float(self.pin_length.get()),
                rotate_z=float(self.rotate_z.get()),
                socket_holes=bool(self.socket_holes.get()),
            )
            self.after(0, self._finish_success, report)
        except Exception as exc:
            self.after(0, self._finish_error, exc)

    def _finish_success(self, report: dict) -> None:
        self.split_button.configure(state=tk.NORMAL)
        self.status.set("Done.")
        self.output_text.insert(tk.END, json.dumps(report, indent=2))
        messagebox.showinfo("Finished", "STL split finished. Check the output folder.")

    def _finish_error(self, exc: Exception) -> None:
        self.split_button.configure(state=tk.NORMAL)
        self.status.set("Error.")
        messagebox.showerror("Split failed", str(exc))


if __name__ == "__main__":
    SplitterApp().mainloop()
