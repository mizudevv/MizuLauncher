from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox


class TextPrompt(ctk.CTkToplevel):
    def __init__(self, master, title: str, label: str, initial: str = "", password: bool = False):
        super().__init__(master)
        self.title(title)
        self.geometry("440x240")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=14, weight="bold")).pack(padx=20, pady=(25, 10), anchor="w")
        self.entry = ctk.CTkEntry(self, height=42, show="*" if password else "")
        self.entry.pack(fill="x", padx=20)
        self.entry.insert(0, initial)
        self.entry.focus_set()
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(row, text="Anuluj", command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row, text="OK", command=self.accept).pack(side="right")
        self.bind("<Return>", lambda _e: self.accept())
        self.bind("<Escape>", lambda _e: self.destroy())

    def accept(self):
        self.result = self.entry.get().strip()
        self.destroy()


def ask_string(master, title: str, label: str, initial: str = "", password: bool = False):
    d = TextPrompt(master, title, label, initial, password=password)
    master.wait_window(d)
    return d.result


def error(master, title: str, message: str):
    messagebox.showerror(title, message, parent=master)


def info(master, title: str, message: str):
    messagebox.showinfo(title, message, parent=master)


def confirm(master, title: str, message: str) -> bool:
    return messagebox.askyesno(title, message, parent=master)
