PALETTES = {
    "dark": {
        "bg": "#090909", "bg2": "#101010", "panel": "#141414", "panel2": "#1B1B1B",
        "panel3": "#252525", "card": "#171717", "card_hover": "#2B2B2B", "border": "#000000",
        "border_soft": "#343434", "text": "#F2F2F2", "muted": "#A3A3A3", "subtle": "#6F6F6F",
        "accent": "#E9E9E9", "accent_hover": "#FFFFFF", "accent_soft": "#2C2C2C",
        "green": "#8BE28B", "green_soft": "#183118", "red": "#F07A7A", "red_soft": "#321717",
        "orange": "#E7A86B", "yellow": "#E7D56B", "white": "#FFFFFF", "black": "#000000",
        "glass": "#2A2A2A",
    },
    "light": {
        "bg": "#E9E9E9", "bg2": "#F2F2F2", "panel": "#F7F7F7", "panel2": "#E1E1E1",
        "panel3": "#D6D6D6", "card": "#FAFAFA", "card_hover": "#E5E5E5", "border": "#000000",
        "border_soft": "#B5B5B5", "text": "#111111", "muted": "#5D5D5D", "subtle": "#8A8A8A",
        "accent": "#111111", "accent_hover": "#000000", "accent_soft": "#D8D8D8",
        "green": "#2F7D32", "green_soft": "#DCEFD8", "red": "#B12E2E", "red_soft": "#F4D8D8",
        "orange": "#9A5F18", "yellow": "#7C6F0A", "white": "#FFFFFF", "black": "#000000",
        "glass": "#F0F0F0",
    },
}

CURRENT = "dark"
COLORS = PALETTES[CURRENT].copy()

def set_palette(name: str):
    global CURRENT, COLORS
    CURRENT = name if name in PALETTES else "dark"
    COLORS.clear(); COLORS.update(PALETTES[CURRENT])

FONTS = {"hero": 38, "title": 28, "section": 19, "body": 13, "small": 11, "button": 13}
