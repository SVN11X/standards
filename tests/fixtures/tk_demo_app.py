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
