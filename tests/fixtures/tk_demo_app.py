"""A tkinter window with one known UX problem of each kind, for tests/test_desktop_ux.py."""
import tkinter as tk
from tkinter import ttk


class Demo:
    def __init__(self, root):
        root.title("Demo")
        book = ttk.Notebook(root)
        book.pack(fill="both", expand=True)
        today = ttk.Frame(book)
        settings = ttk.Frame(book)
        book.add(today, text="Hoy")
        book.add(settings, text="Ajustes")
        tk.Label(today, text="Texto gris claro", fg="#BBBBBB", bg="#FFFFFF").pack()
        tk.Label(today, text="Letra chica", font=("Segoe UI", 7)).pack()
        row = tk.Frame(today)
        row.pack()
        tk.Button(row, text="A", width=1, padx=0, pady=0, font=("Segoe UI", 6)).pack(side="left")
        tk.Button(row, text="B", width=1, padx=0, pady=0, font=("Segoe UI", 6)).pack(side="left", padx=2)
        clickable = tk.Label(today, text="Haz clic aquí")
        clickable.bind("<Button-1>", lambda e: None)
        clickable.pack()
        tk.Button(today, text="Sin teclado", takefocus=0).pack(pady=20)
        tk.Label(settings, text="Una etiqueta con un texto muy largo que no cabe", width=10, anchor="w").pack()
        ttk.Button(settings, text="Guardar").pack(pady=20)


def build(root):
    return Demo(root)


def build_dialog(root):
    """A dialog whose long bold text pushes its only action below the visible part of the window."""
    top = tk.Toplevel(root)
    canvas = tk.Canvas(top, highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    content = ttk.Frame(canvas, padding=10)
    canvas.create_window((0, 0), window=content, anchor="nw")
    ttk.Label(content, text="Pregunta larga " * 12, wraplength=300, font=("Segoe UI", 12, "bold")).pack(anchor="w")
    ttk.Button(content, text="Siguiente").pack(anchor="e", pady=(400, 0))
    return top


def build_hidden(root):
    """A dialog that is never shown, so nothing can be measured."""
    top = tk.Toplevel(root)
    ttk.Button(top, text="Invisible").pack()
    top.withdraw()
    return top
