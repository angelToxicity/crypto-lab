"""Escritorio de CryptoLab: presentación visual sin dependencias adicionales."""

import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, font, ttk

from .domain import CryptoLabError
from .forms import MODULES, FormController

COLORS = {
    "background": "#F5F6F8", "surface": "#FFFFFF", "ink": "#192D39",
    "muted": "#536875", "line": "#DCE4E9", "accent": "#155E75",
    "accent_dark": "#10485B", "soft": "#EAF3F6",
    "good": "#216444", "bad": "#A13239",
}
MODULE_DETAILS = {
    "rsa": ("CONFIDENCIALIDAD", "RSA · perfiles explícitos",
            "El límite del mensaje se comprueba con el tamaño real de la clave seleccionada."),
    "hash": ("HUELLA DIGITAL", "SHA-256",
             "La huella se muestra en pantalla y se guarda en formato hexadecimal."),
    "certificate": ("IDENTIDAD Y CLAVES", "RSA-3072 · X.509 v3",
                    "La clave privada se protege con tu contraseña. Conserva los cuatro archivos generados."),
    "sign": ("AUTENTICIDAD DEL DOCUMENTO", "RSA · SHA-256",
             "La firma se guarda en un archivo separado. El documento original se conserva."),
    "verify": ("INTEGRIDAD Y AUTENTICIDAD", "RSA · SHA-256",
               "La validez de la firma y la vigencia del certificado se informan por separado."),
    "tamper": ("DEMOSTRACIÓN DE INTEGRIDAD", "Original y copia",
               "Se comprueba el original antes de crear y verificar una copia modificada."),
}


def _rounded_points(width, height, radius=20):
    return (
        radius, 1, width - radius, 1, width - 1, 1, width - 1, radius,
        width - 1, height - radius, width - 1, height - 1,
        width - radius, height - 1, radius, height - 1, 1, height - 1,
        1, height - radius, 1, radius, 1, 1,
    )


class RoundedCard(tk.Canvas):
    """Tarjeta que ajusta su altura al contenido, sin imágenes ni archivos de tema."""

    def __init__(self, parent):
        super().__init__(parent, background=COLORS["background"], highlightthickness=0)
        self._outline = self.create_polygon(
            0, 0, 0, 0, 0, 0, smooth=True,
            fill=COLORS["surface"], outline=COLORS["line"],
        )
        self.body = ttk.Frame(self, style="Card.TFrame")
        self._body_id = self.create_window(22, 22, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._resize)

    def _resize(self, event=None):
        width = self.winfo_width()
        if width < 48:
            return
        self.itemconfigure(self._body_id, width=width - 44)
        height = self.body.winfo_reqheight() + 44
        self.configure(height=height)
        self.coords(self._outline, *_rounded_points(width, height))


class CryptoLabWindow(tk.Tk):
    def __init__(self, controller: FormController, version: str):
        super().__init__()
        self._controller = controller
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._results = queue.Queue()
        self._busy = False
        self._closing = False
        self._module = MODULES[0]
        self._variables = {}
        self._navigation = {}
        self._inputs = []
        self._columns = 2
        self._version = version.split(" (Library:")[0]

        self.title("CryptoLab | Criptografía y firmas digitales")
        width = max(760, min(1180, self.winfo_screenwidth() - 80))
        height = max(540, min(840, self.winfo_screenheight() - 100))
        self.geometry("{}x{}".format(width, height))
        self.minsize(760, 540)
        self.configure(background=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self._request_close)
        self._configure_styles()
        self._build_layout()
        self._select_module(MODULES[0])
        self._poll_id = self.after(100, self._poll_results)

    def _configure_styles(self):
        available = set(font.families())
        default = font.nametofont("TkDefaultFont").actual("family")
        self._family = next((name for name in ("Inter", "Segoe UI", "Noto Sans", "Ubuntu", "DejaVu Sans")
                             if name in available), default)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(family=self._family, size=10)
        self.option_add("*TCombobox*Listbox.font", (self._family, 10))
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Background.TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["surface"])
        self._images = []

        for name, background, foreground, padding in (
            ("Primary", COLORS["accent"], "white", (9, 6)),
            ("Browse", COLORS["soft"], COLORS["accent"], (6, 5)),
            ("Nav", COLORS["surface"], COLORS["muted"], (6, 6)),
            ("Selected.Nav", COLORS["soft"], COLORS["accent"], (6, 6)),
        ):
            style.configure(name + ".TButton", background=COLORS["surface"], foreground=foreground,
                            borderwidth=0, relief="flat", padding=padding, font=(self._family, 10),
                            anchor="w" if "Nav" in name else "center")
            hover = COLORS["accent_dark"] if name == "Primary" else COLORS["soft"]
            element = name + ".rounded"
            style.element_create(element, "image", self._rounded_image(background),
                                 ("disabled", self._rounded_image(COLORS["line"])),
                                 ("active", self._rounded_image(hover)),
                                 ("focus", self._rounded_image(background, COLORS["accent"])),
                                 border=7, sticky="nsew")
            style.layout(name + ".TButton", [(element, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
            ]})])
            style.map(name + ".TButton", foreground=[("disabled", COLORS["muted"])],
                      background=[("active", COLORS["surface"]), ("disabled", COLORS["surface"])])

        style.element_create("Field.rounded", "image", self._rounded_image(COLORS["background"], COLORS["line"]),
                             ("focus", self._rounded_image(COLORS["background"], COLORS["accent"])),
                             border=7, sticky="nsew")
        arrow = tk.PhotoImage(master=self, width=14, height=14)
        for row in range(4):
            arrow.put(COLORS["muted"], to=(3 + row, 5 + row, 11 - row, 6 + row))
        self._images.append(arrow)
        style.element_create("Field.downarrow", "image", arrow, sticky="")
        for name in ("Field.TEntry", "Field.TCombobox"):
            prefix = "Combobox" if name.endswith("TCombobox") else "Entry"
            children = [(prefix + ".padding", {"sticky": "nsew", "children": [
                (prefix + ".textarea", {"sticky": "nsew"})
            ]})]
            if prefix == "Combobox":
                children.insert(0, ("Field.downarrow", {"side": "right", "sticky": ""}))
            style.layout(name, [("Field.rounded", {"sticky": "nsew", "children": children})])
            style.configure(name, fieldbackground=COLORS["background"], foreground=COLORS["ink"],
                            background=COLORS["surface"], borderwidth=0, relief="flat",
                            padding=(7, 6), font=(self._family, 10), arrowcolor=COLORS["muted"])
            style.map(name, foreground=[("disabled", COLORS["muted"]), ("readonly", COLORS["ink"])],
                      background=[("readonly", COLORS["surface"]), ("disabled", COLORS["surface"])],
                      fieldbackground=[("readonly", COLORS["background"]), ("disabled", COLORS["background"])],
                      selectbackground=[("readonly", COLORS["background"])],
                      selectforeground=[("readonly", COLORS["ink"])])
        style.configure("Vertical.TScrollbar", background=COLORS["line"], borderwidth=0,
                        troughcolor=COLORS["background"], arrowcolor=COLORS["muted"])
        style.configure("Work.Horizontal.TProgressbar", background=COLORS["accent"],
                        troughcolor=COLORS["soft"], borderwidth=0)

    def _rounded_image(self, fill, outline=None):
        """Imagen pequeña extensible por ttk; se dibuja con el propio Tk."""
        radius, size = 7, 18
        image = tk.PhotoImage(master=self, width=size, height=size)
        for inset, color in ((0, outline or fill), (1, fill)):
            corner = radius - inset
            for y in range(inset, size - inset):
                distance = max(corner - (y - inset), corner - (size - inset - 1 - y), 0)
                left = inset + round(corner - (corner ** 2 - distance ** 2) ** 0.5)
                image.put(color, to=(left, y, size - left, y + 1))
        self._images.append(image)
        return image

    def _label(self, parent, text, size=10, color="ink", background="surface", bold=False, **options):
        options.setdefault("anchor", "w")
        return tk.Label(parent, text=text, background=COLORS[background], foreground=COLORS[color],
                        font=(self._family, size, "bold" if bold else "normal"), **options)

    def _build_layout(self):
        header = tk.Frame(self, background=COLORS["surface"], padx=26, pady=17)
        header.pack(fill="x")
        logo = tk.Canvas(header, width=42, height=42, background=COLORS["surface"], highlightthickness=0)
        logo.pack(side="left", padx=(0, 13))
        logo.create_polygon(*_rounded_points(42, 42, 14), smooth=True, fill=COLORS["accent"], outline="")
        for box in ((10, 8, 32, 34), (14, 12, 28, 33), (18, 16, 24, 31)):
            logo.create_arc(*box, start=0, extent=180, style="arc", outline="white", width=1.5)
        for points in ((10, 21, 10, 28, 8, 32), (14, 23, 14, 30, 12, 35),
                       (18, 24, 18, 31, 16, 35), (24, 22, 24, 30, 27, 34), (31, 21, 31, 28, 33, 31)):
            logo.create_line(*points, fill="white", width=1.5, smooth=True, capstyle="round")
        brand = ttk.Frame(header, style="Card.TFrame")
        brand.pack(side="left")
        self._label(brand, "CryptoLab", size=17, bold=True).pack(anchor="w")
        self._label(brand, "Criptografía y firmas digitales · UCV", size=9, color="muted").pack(anchor="w", pady=(2, 0))
        self._label(header, "OpenSSL disponible", size=9, color="accent", background="soft",
                    padx=12, pady=7).pack(side="right")

        footer = tk.Frame(self, background=COLORS["surface"], padx=26, pady=11)
        footer.pack(side="bottom", fill="x")
        self._label(footer, "Procesamiento local", size=9, color="muted").pack(side="left")
        self._status = self._label(footer, self._version, size=9, color="muted", anchor="e")
        self._status.pack(side="right")

        body = ttk.Frame(self, style="Background.TFrame")
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, background=COLORS["surface"], width=224, padx=12, pady=24)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._label(sidebar, "LABORATORIO", size=9, color="muted").pack(anchor="w", padx=12, pady=(0, 14))
        for index, module in enumerate(MODULES, 1):
            button = ttk.Button(
                sidebar, text="{:02d}    {}".format(index, module.title), style="Nav.TButton",
                command=lambda item=module: self._select_module(item),
            )
            button.pack(fill="x", pady=3)
            self._navigation[module.name] = button
        self._label(sidebar, "Procesamiento local\nSin cuenta ni conexión", size=9, color="muted",
                    justify="left", anchor="w").pack(side="bottom", anchor="w", padx=12, pady=10)
        tk.Frame(body, width=1, background=COLORS["line"]).pack(side="left", fill="y")

        viewport = ttk.Frame(body, style="Background.TFrame")
        viewport.pack(side="left", fill="both", expand=True)
        self._canvas = tk.Canvas(viewport, background=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._content = ttk.Frame(self._canvas, style="Background.TFrame", padding=(30, 26, 30, 26))
        self._canvas_item = self._canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", lambda event: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._resize_canvas)
        self.bind("<MouseWheel>", self._scroll)
        self.bind("<Button-4>", lambda event: self._canvas.yview_scroll(-3, "units"))
        self.bind("<Button-5>", lambda event: self._canvas.yview_scroll(3, "units"))

    def _resize_canvas(self, event):
        self._canvas.itemconfigure(self._canvas_item, width=event.width)
        if hasattr(self, "_description"):
            self._description.configure(wraplength=max(280, event.width - 70))
        if hasattr(self, "_help_label"):
            self._help_label.configure(wraplength=max(250, event.width - 120))
        columns = 2 if event.width >= 700 else 1
        if columns != self._columns:
            self._columns = columns
            if hasattr(self, "_fields"):
                self._render_fields()

    def _scroll(self, event):
        self._canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")

    def _select_module(self, module):
        self._module = module
        for name, button in self._navigation.items():
            button.configure(style="Selected.Nav.TButton" if name == module.name else "Nav.TButton")
        for widget in self._content.winfo_children():
            widget.destroy()
        self._variables = {field.name: tk.StringVar(value=field.default) for field in module.fields}
        section, profile, help_text = MODULE_DETAILS[module.name]
        self._label(self._content, section, size=9, color="accent", background="background").pack(anchor="w")
        self._label(self._content, module.title, size=23, background="background").pack(anchor="w", pady=(7, 7))
        self._description = self._label(self._content, module.description, color="muted",
                                       background="background", wraplength=760, justify="left")
        self._description.pack(anchor="w", pady=(0, 22))

        card = RoundedCard(self._content)
        card.pack(fill="x")
        card_head = ttk.Frame(card.body, style="Card.TFrame")
        card_head.pack(fill="x", pady=(0, 17))
        self._label(card_head, "Archivos y opciones", size=11, bold=True).pack(side="left")
        self._profile = self._label(card_head, profile, size=9, color="accent", background="soft", padx=9, pady=5)
        self._profile.pack(side="right")
        tk.Frame(card.body, height=1, background=COLORS["line"]).pack(fill="x")
        self._fields = ttk.Frame(card.body, style="Card.TFrame")
        self._fields.pack(fill="x", pady=(10, 4))
        self._help_label = self._label(card.body, help_text, size=9, color="muted",
                                       justify="left", wraplength=650)
        self._help_label.pack(anchor="w", fill="x", pady=(8, 0))
        actions = ttk.Frame(card.body, style="Card.TFrame")
        actions.pack(fill="x", pady=(20, 0))
        self._run_button = ttk.Button(actions, style="Primary.TButton", command=self._start_operation)
        self._run_button.pack(side="left")
        self._label(actions, "En este equipo", size=9, color="muted").pack(side="left", padx=14)
        self._progress = ttk.Progressbar(actions, length=90, mode="indeterminate", style="Work.Horizontal.TProgressbar")

        self._result_box = tk.Frame(card.body, background=COLORS["surface"])
        self._result_marker = tk.Frame(self._result_box, width=3, background=COLORS["good"])
        self._result_marker.pack(side="left", fill="y", padx=(0, 13))
        result_body = ttk.Frame(self._result_box, style="Card.TFrame")
        result_body.pack(side="left", fill="both", expand=True)
        self._result_heading = self._label(result_body, "Resultado", size=11, bold=True, color="good")
        self._result_heading.pack(anchor="w", pady=(0, 6))
        result_area = ttk.Frame(result_body, style="Card.TFrame")
        result_area.pack(fill="both", expand=True)
        self._result = tk.Text(result_area, height=5, width=1, wrap="word", font=(self._family, 10),
                               background=COLORS["surface"], foreground=COLORS["muted"],
                               relief="flat", highlightthickness=0, state="disabled")
        self._result.pack(side="left", fill="both", expand=True)
        result_scroll = ttk.Scrollbar(result_area, command=self._result.yview)
        result_scroll.pack(side="right", fill="y")
        self._result.configure(yscrollcommand=result_scroll.set)
        self._render_fields()
        self._inputs[0].focus_set()
        self._canvas.yview_moveto(0)

    def _action_text(self):
        if self._module.name == "rsa":
            return self._variables["action"].get().replace("texto", "mensaje")
        return self._module.title

    def _render_fields(self):
        for widget in self._fields.winfo_children():
            widget.destroy()
        self._inputs = []
        values = {name: variable.get() for name, variable in self._variables.items()}
        visible = [field for field in self._module.fields if field.visible(values)]
        visible.sort(key=lambda field: field.kind != "choice")
        self._profile.configure(text=values.get("padding", values.get("algorithm", MODULE_DETAILS[self._module.name][1])))
        self._run_button.configure(text=self._action_text())
        for column in range(2):
            self._fields.columnconfigure(column, weight=1 if column < self._columns else 0,
                                          uniform="fields" if column < self._columns else "")
        row = column = 0
        for index, field in enumerate(visible):
            wide = field.name in ("message", "old_text", "new_text") or (index == len(visible) - 1 and column == 0)
            if wide and column:
                row, column = row + 1, 0
            span = self._columns if wide else 1
            group = ttk.Frame(self._fields, style="Card.TFrame")
            group.grid(row=row, column=column, columnspan=span, sticky="ew",
                       padx=(0 if column == 0 else 8, 8 if span == 1 and self._columns == 2 and column == 0 else 0),
                       pady=(8, 9))
            label = field.label
            if self._module.name == "rsa" and field.name == "key":
                label = "Clave privada PEM" if values["action"] == "Descifrar archivo" else "Clave pública PEM"
            label += " (opcional)" if not field.required else ""
            self._label(group, label, size=9, color="muted", wraplength=270, justify="left").pack(anchor="w", pady=(0, 7))
            control = ttk.Frame(group, style="Card.TFrame")
            control.pack(fill="x")
            control.columnconfigure(0, weight=1)
            variable = self._variables[field.name]
            if field.kind == "choice":
                entry = ttk.Combobox(control, width=1, textvariable=variable, values=field.choices,
                                     state="readonly", style="Field.TCombobox")
                entry.bind("<<ComboboxSelected>>", lambda event: self._render_fields())
            else:
                entry = ttk.Entry(control, width=1, textvariable=variable, style="Field.TEntry",
                                  show="*" if field.kind == "password" else "")
            entry.grid(row=0, column=0, sticky="ew")
            self._inputs.append(entry)
            if field.kind in ("file", "save", "folder"):
                button = ttk.Button(control, text="Elegir", width=6, style="Browse.TButton",
                                    command=lambda item=field: self._browse(item))
                button.grid(row=0, column=1, padx=(8, 0))
                self._inputs.append(button)
            column += span
            if column >= self._columns:
                row, column = row + 1, 0

    def _browse(self, field):
        if field.kind == "folder":
            value = filedialog.askdirectory(parent=self, title=field.label)
        elif field.kind == "save":
            value = filedialog.asksaveasfilename(parent=self, title=field.label, initialfile=field.suggestion)
        else:
            value = filedialog.askopenfilename(parent=self, title=field.label)
        if value:
            self._variables[field.name].set(value)

    def _start_operation(self):
        if self._busy:
            return
        values = {name: variable.get() for name, variable in self._variables.items()}
        for field in self._module.fields:
            if field.kind == "password":
                self._variables[field.name].set("")
        self._set_busy(True)
        future = self._executor.submit(self._execute, self._module, values)
        future.add_done_callback(self._results.put)

    def _execute(self, module, values):
        try:
            return self._controller.execute(module.name, values)
        finally:
            for field in module.fields:
                if field.kind == "password":
                    values[field.name] = ""

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in self._navigation.values():
            button.configure(state=state)
        for entry in self._inputs:
            entry.configure(state="disabled" if busy else "readonly" if isinstance(entry, ttk.Combobox) else "normal")
        self._run_button.configure(state=state, text="Procesando…" if busy else self._action_text())
        self._status.configure(text="Procesando los archivos…" if busy else self._version)
        if busy:
            self._result_box.pack_forget()
            self._progress.pack(side="right", padx=5)
            self._progress.start(20)
        else:
            self._progress.stop()
            self._progress.pack_forget()

    def _poll_results(self):
        try:
            future = self._results.get_nowait()
        except queue.Empty:
            self._poll_id = self.after(100, self._poll_results)
            return
        try:
            result = future.result()
            self._show_result(result.message, result.success)
        except CryptoLabError as error:
            self._show_result(str(error), False)
        except Exception as error:
            self._show_result("Error inesperado ({}): {}".format(type(error).__name__, error), False)
        self._set_busy(False)
        if self._closing:
            self._request_close()
            return
        self._poll_id = self.after(100, self._poll_results)

    def _show_result(self, message, success):
        color = COLORS["good"] if success else COLORS["bad"]
        self._result_marker.configure(background=color)
        self._result_heading.configure(text="Operación completada" if success else "Revisa los datos", foreground=color)
        self._result.configure(state="normal", height=min(8, max(3, len(message.splitlines()) + 1)))
        self._result.delete("1.0", "end")
        self._result.insert("1.0", message)
        self._result.configure(state="disabled")
        self._result_box.pack(fill="x", pady=(22, 0))
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1)

    def _request_close(self):
        if self._busy:
            self._closing = True
            self._status.configure(text="Esperando a que finalice la operación antes de cerrar…")
            return
        self.after_cancel(self._poll_id)
        self._executor.shutdown(wait=False)
        self.destroy()

