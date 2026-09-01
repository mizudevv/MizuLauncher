import sys

from startup_gate import required_update_gate


if __name__ == "__main__":
    if not required_update_gate():
        sys.exit(0)

    import customtkinter as ctk
    from mizulauncher.ui.main_window import MizuLauncher

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = MizuLauncher()
    app.mainloop()
