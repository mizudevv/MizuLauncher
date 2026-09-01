from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import json

from .config import DATA_DIR

LAYOUT_FILE = DATA_DIR / "layout.json"

DEFAULT_LAYOUT = {
    'version': 1,
    'design': {'width': 1280, 'height': 760},
    'templates': {
        'game_primary': {
            'type': 'button', 'text': '{{game.primary_label}}', 'action': 'game.primary',
            'game_binding': 'context', 'fg': '#F2F2F2', 'text_color': '#0A0A0A',
            'hover': '#FFFFFF', 'border_color': '#000000', 'border_width': 2,
            'radius': 12, 'height': 42, 'font_size': 13,
        },
        'game_uninstall': {
            'type': 'button', 'text': 'Odinstaluj', 'action': 'game.uninstall',
            'game_binding': 'context', 'fg': '#281515', 'text_color': '#F07A7A',
            'hover': '#5A2020', 'border_color': '#000000', 'border_width': 2,
            'radius': 12, 'height': 42, 'font_size': 13,
        },
        'game_path': {
            'type': 'button', 'text': 'Lokalizacja', 'action': 'game.path',
            'game_binding': 'context', 'fg': '#202020', 'text_color': '#F2F2F2',
            'hover': '#2E2E2E', 'border_color': '#000000', 'border_width': 2,
            'radius': 12, 'height': 42, 'font_size': 13,
        },
    },
    'pages': {
        'home': {
            'label': 'Home',
            'elements': [
                {'id': 'home_featured', 'type': 'featured_game', 'x': 2.0, 'y': 2.0, 'w': 96.0, 'h': 48.0, 'radius': 24},
                {'id': 'home_title', 'type': 'section_title', 'text': 'Odkryj gry', 'x': 2.0, 'y': 53.0, 'w': 60.0, 'h': 5.5, 'font_size': 22},
                {'id': 'home_subtitle', 'type': 'text', 'text': 'Przewiń niżej, wyszukaj grę i otwórz jej szczegóły.', 'x': 2.0, 'y': 58.0, 'w': 70.0, 'h': 4.5, 'font_size': 13, 'text_color': '#9A9A9A'},
                {'id': 'home_games', 'type': 'game_list', 'x': 2.0, 'y': 63.5, 'w': 96.0, 'h': 70.0, 'card_w': 30.5, 'columns': 3, 'show_actions': True, 'search_enabled': True, 'search_placeholder': 'Szukaj po nazwie, autorze, kategorii lub tagach...', 'template_primary': 'game_primary', 'template_uninstall': 'game_uninstall', 'template_path': 'game_path'},
            ],
        },
        'library': {
            'label': 'Library',
            'elements': [
                {'id': 'library_title', 'type': 'section_title', 'text': 'Biblioteka', 'x': 2.0, 'y': 2.0, 'w': 60.0, 'h': 6.0, 'font_size': 28},
                {'id': 'library_games', 'type': 'game_list', 'x': 2.0, 'y': 10.0, 'w': 96.0, 'h': 88.0, 'card_w': 30.5, 'columns': 3, 'show_actions': True, 'installed_only': True, 'search_enabled': True, 'search_placeholder': 'Szukaj w bibliotece...', 'template_primary': 'game_primary', 'template_uninstall': 'game_uninstall', 'template_path': 'game_path'},
            ],
        },
        'details': {
            'label': 'Game Details',
            'elements': [
                {'id': 'details', 'type': 'game_detail', 'x': 2.0, 'y': 2.0, 'w': 96.0, 'h': 96.0, 'template_primary': 'game_primary', 'template_uninstall': 'game_uninstall', 'template_path': 'game_path'},
            ],
        },
    },
}


def deep_merge(base, incoming):
    if isinstance(base, dict) and isinstance(incoming, dict):
        out = deepcopy(base)
        for k, v in incoming.items():
            out[k] = deep_merge(out[k], v) if k in out else deepcopy(v)
        return out
    return deepcopy(incoming)


def load_layout() -> dict:
    LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LAYOUT_FILE.exists():
        save_layout(DEFAULT_LAYOUT)
        return deepcopy(DEFAULT_LAYOUT)
    try:
        data = json.loads(LAYOUT_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError
        return deep_merge(DEFAULT_LAYOUT, data)
    except Exception:
        save_layout(DEFAULT_LAYOUT)
        return deepcopy(DEFAULT_LAYOUT)


def save_layout(layout: dict) -> None:
    LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_FILE.write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding='utf-8')


def export_layout(layout: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding='utf-8')


def import_layout(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or 'pages' not in data:
        raise ValueError('Niepoprawny plik layoutu.')
    return deep_merge(DEFAULT_LAYOUT, data)


def make_element_id(prefix: str, elements: list[dict]) -> str:
    existing = {e.get('id') for e in elements}
    i = 1
    while f'{prefix}_{i}' in existing:
        i += 1
    return f'{prefix}_{i}'
