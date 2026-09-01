from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path

import customtkinter as ctk

from ..layout_engine import load_layout, save_layout
from ..models import Game
from .theme import COLORS, FONTS


def _num(v, default=0.0):
    try: return float(v)
    except Exception: return default


def _game_context(app: 'MizuLauncher', game: Game | None):
    if not game: return {}
    installed = app.manager.is_installed(game)
    path = app.manager.installs / game.id
    return {
        'game.name': game.name,
        'game.version': game.version,
        'game.developer': game.developer,
        'game.description': game.description,
        'game.category': game.category,
        'game.id': game.id,
        'game.path': str(path),
        'game.primary_label': ('Aktualizuj' if app.manager.update_available(game) else 'Graj') if installed else 'Zainstaluj',
        'game.install_label': ('Aktualizacja dostępna' if app.manager.update_available(game) else 'Zainstalowana') if installed else 'Zainstaluj',
        'game.installed': installed,
        'game.installed_version': app.manager.installed_version(game),
        'game.update_available': app.manager.update_available(game),
    }


def _substitute(text: str, ctx: dict):
    out = str(text or '')
    for k, v in ctx.items():
        out = out.replace('{{'+k+'}}', str(v))
    return out


def _page_container(app, page_name):
    page = app.layout.get('pages', {}).get(page_name) or app.layout.get('pages', {}).get('home')
    return page or {'elements': []}


def _place(widget, el):
    x=max(0,min(100,_num(el.get('x'),2)))/100
    y=max(0,min(100,_num(el.get('y'),2)))/100
    w=max(.001,min(100,_num(el.get('w'),20)))/100
    h=max(.001,min(100,_num(el.get('h'),10)))/100
    widget.place(relx=x,rely=y,relwidth=w,relheight=h)


def _button_style(data):
    return dict(
        fg_color=data.get('fg') or COLORS['panel2'],
        hover_color=data.get('hover') or COLORS['card_hover'],
        text_color=data.get('text_color') or COLORS['text'],
        corner_radius=int(_num(data.get('radius'),12)),
        border_width=int(_num(data.get('border_width'),1)),
        border_color=data.get('border_color') or COLORS['black'],
    )


def _resolve_game(app, binding='context', fixed_id=''):
    if binding == 'selected' and app.selected_game:
        return app.selected_game
    if binding == 'fixed' and fixed_id:
        return next((g for g in app.games if g.id == fixed_id), None)
    return app.selected_game


def perform_action(app, action, game=None, data=None):
    data = data or {}
    game = game or _resolve_game(app, data.get('game_binding','context'), data.get('game_id',''))
    if action == 'none': return
    if action == 'navigate.home': app.show_view('home'); return
    if action == 'navigate.library': app.show_view('library'); return
    if action == 'navigate.settings': app.show_view('settings'); return
    if action == 'navigate.page':
        target = data.get('target_page', 'home')
        if target in getattr(app, 'layout', {}).get('pages', {}): app.show_view(target)
        return
    if action == 'account': app.open_account_manager(); return
    if action == 'refresh': app.refresh_games(); return
    if action == 'open_url':
        url=data.get('url','').strip()
        if url: webbrowser.open(url)
        return
    if not game:
        return
    if action == 'game.details': app.open_game_details(game); return
    if action in {'game.primary','game.install'}:
        app.install_or_launch(game, return_to_details=(app.current_view == 'details')); return
    if action == 'game.play':
        app.manager.launch(game); return
    if action == 'game.uninstall':
        app.uninstall_game(game); return
    if action == 'game.path':
        app.open_game_location(game); return
    if action == 'game.homepage':
        app.open_game_homepage(game); return


def render_element(app, parent, el, page_name):
    typ=el.get('type','text')
    selected_game=app.selected_game
    ctx=_game_context(app, selected_game)
    common_fg=el.get('fg') or 'transparent'
    if typ in {'text','section_title'}:
        widget=ctk.CTkLabel(parent,text=_substitute(el.get('text',''),ctx),fg_color=common_fg,text_color=el.get('text_color') or COLORS['text'],anchor='w',justify='left',wraplength=700,font=ctk.CTkFont(size=int(_num(el.get('font_size'),16)),weight='bold' if typ=='section_title' else 'normal'))
    elif typ=='button':
        template=app.layout.get('templates',{}).get(el.get('template_id',''),{}) if el.get('template_id') else {}
        data={**template,**el}
        action=data.get('action','none')
        target=_resolve_game(app,data.get('game_binding','context'),data.get('game_id',''))
        widget=ctk.CTkButton(parent,text=_substitute(data.get('text','Przycisk'),_game_context(app,target)),command=lambda a=action,t=target,d=data: perform_action(app,a,t,d),height=int(_num(data.get('height'),42)),**_button_style(data))
    elif typ=='image':
        widget=ctk.CTkLabel(parent,text='',fg_color=common_fg,corner_radius=int(_num(el.get('radius'),12)))
        url=el.get('image_url','')
        def cb(img,w=widget):
            try:w.configure(image=img,text='')
            except:pass
        app.image_loader.request(url or '',el.get('alt','Mizu'),(max(50,int(parent.winfo_width()*max(.01,_num(el.get('w'),20)/100))),max(50,int(parent.winfo_height()*max(.01,_num(el.get('h'),10)/100)))),'banner',cb)
    elif typ=='separator':
        widget=ctk.CTkFrame(parent,fg_color=el.get('fg') or COLORS['black'],corner_radius=0)
    elif typ=='spacer':
        widget=ctk.CTkFrame(parent,fg_color='transparent')
    elif typ=='featured_game':
        widget=build_featured(app,parent,el)
    elif typ=='game_list':
        widget=build_game_list(app,parent,el,page_name)
    elif typ=='game_detail':
        widget=build_game_detail(app,parent,el)
    else:
        widget=ctk.CTkFrame(parent,fg_color=common_fg,corner_radius=int(_num(el.get('radius'),12)))
    _place(widget,el)
    return widget


def build_featured(app,parent,el):
    games=[g for g in app.games if g.enabled and g.featured] or [g for g in app.games if g.enabled][:1]
    outer=ctk.CTkFrame(parent,fg_color=COLORS['panel'],corner_radius=int(_num(el.get('radius'),24)),border_width=2,border_color=COLORS['black'])
    if not games:
        ctk.CTkLabel(outer,text='Brak wyróżnionej gry',font=ctk.CTkFont(size=22,weight='bold')).pack(anchor='w',padx=24,pady=(28,5)); return outer
    game=games[0]
    outer.bind('<Button-1>',lambda _e,g=game:app.open_game_details(g))
    hero=ctk.CTkLabel(outer,text='',fg_color=COLORS['panel2'],corner_radius=int(_num(el.get('radius'),24))); hero.pack(fill='both',expand=True,padx=2,pady=2)
    app.image_loader.request(game.banner_url,game.name,(max(500,parent.winfo_width()),max(260,parent.winfo_height())),'hero',lambda img,w=hero:w.configure(image=img,text=''))
    overlay=ctk.CTkFrame(outer,fg_color='transparent',corner_radius=0); overlay.place(relx=.045,rely=.08,relwidth=.60,relheight=.84)
    ctk.CTkLabel(overlay,text='WYRÓŻNIONA GRA',font=ctk.CTkFont(size=10,weight='bold'),text_color='#D5D5D5').pack(anchor='w')
    ctk.CTkLabel(overlay,text=game.name,font=ctk.CTkFont(size=36,weight='bold'),text_color='#FFFFFF',wraplength=600,justify='left').pack(anchor='w',pady=(12,4))
    ctk.CTkLabel(overlay,text=f'v{game.version}  •  {game.developer}',text_color='#D0D0D0').pack(anchor='w')
    ctk.CTkLabel(overlay,text=game.description or '',text_color='#BEBEBE',wraplength=600,justify='left').pack(anchor='w',pady=(10,18))
    action=app.layout.get('templates',{}).get(el.get('template_primary','game_primary'),{})
    btn=ctk.CTkButton(overlay,text=_substitute(action.get('text','{{game.primary_label}}'),_game_context(app,game)),command=lambda g=game,d=action:perform_action(app,d.get('action','game.primary'),g,d),height=int(_num(action.get('height'),44)),**_button_style(action)); btn.pack(anchor='w')
    return outer


def build_game_list(app, parent, el, page_name="home"):
    """Render a responsive game catalog.

    installed_only=True makes the element behave as the user's Library.
    search_enabled=True adds a local filter bar above the catalog.
    """
    wrapper = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
    wrapper.pack_propagate(False)

    # Runtime-enforced catalog semantics. Remote/custom layouts may be stale,
    # so Home is always the full catalog and Library is always installed-only.
    # The Home catalog always gets a name/author search field as well.
    if page_name == 'library':
        installed_only = True
        search_enabled = True
    elif page_name == 'home':
        installed_only = False
        search_enabled = True
    else:
        installed_only = bool(el.get('installed_only', False))
        search_enabled = bool(el.get('search_enabled', False))
    search_var = ctk.StringVar(value="")

    header = ctk.CTkFrame(wrapper, fg_color="transparent", corner_radius=0)
    header.pack(fill='x', padx=4, pady=(0, 10))

    if search_enabled:
        search_box = ctk.CTkFrame(header, fg_color=COLORS['panel'], corner_radius=16,
                                  border_width=2, border_color=COLORS['black'])
        search_box.pack(fill='x')
        ctk.CTkLabel(search_box, text='⌕', text_color=COLORS['muted'],
                     font=ctk.CTkFont(size=20, weight='bold')).pack(side='left', padx=(14, 4))
        entry = ctk.CTkEntry(
            search_box,
            textvariable=search_var,
            placeholder_text=el.get('search_placeholder', 'Szukaj gry...'),
            border_width=0,
            fg_color='transparent',
            height=44,
            font=ctk.CTkFont(size=14),
        )
        entry.pack(side='left', fill='x', expand=True, padx=(0, 12), pady=3)

    count_label = ctk.CTkLabel(header, text='', text_color=COLORS['muted'])
    count_label.pack(anchor='w', padx=4, pady=(8, 0))

    holder = ctk.CTkScrollableFrame(
        wrapper,
        fg_color='transparent',
        orientation='vertical',
        corner_radius=0,
    )
    holder.pack(fill='both', expand=True)

    columns = max(1, int(_num(el.get('columns'), 3)))
    gap = int(_num(el.get('gap'), 1.0))
    primary_template = app.layout.get('templates', {}).get(el.get('template_primary', 'game_primary'), {})
    uninstall_template = app.layout.get('templates', {}).get(el.get('template_uninstall', 'game_uninstall'), {})
    path_template = app.layout.get('templates', {}).get(el.get('template_path', 'game_path'), {})

    def matches(game, query):
        if not query:
            return True
        q = query.lower().strip()
        # User-facing catalog search intentionally matches ONLY game name and author.
        haystack = f"{game.name} {game.developer}".lower()
        return q in haystack

    def rebuild(*_):
        for child in holder.winfo_children():
            child.destroy()
        query = search_var.get().strip()
        candidates = [g for g in app.games if g.enabled]
        if installed_only:
            candidates = [g for g in candidates if app.manager.is_installed(g)]
        filtered = [g for g in candidates if matches(g, query)]
        noun = 'gra' if len(filtered) == 1 else 'gier'
        if installed_only:
            count_label.configure(text=f'{len(filtered)} {noun} zainstalowanych')
        else:
            count_label.configure(text=f'{len(filtered)} {noun}')

        if not filtered:
            empty = ctk.CTkFrame(holder, fg_color=COLORS['panel'], corner_radius=18,
                                 border_width=2, border_color=COLORS['black'])
            empty.grid(row=0, column=0, sticky='ew', padx=6, pady=10)
            holder.grid_columnconfigure(0, weight=1)
            title = 'Brak zainstalowanych gier' if installed_only else ('Nie znaleziono gry' if query else 'Katalog jest pusty')
            subtitle = ('Pobierz grę z Home, aby pojawiła się w Bibliotece.' if installed_only
                        else ('Spróbuj innej nazwy lub autora.' if query else 'Na razie nie ma żadnych gier w katalogu.'))
            ctk.CTkLabel(empty, text=title, font=ctk.CTkFont(size=21, weight='bold')).pack(anchor='w', padx=22, pady=(22, 4))
            ctk.CTkLabel(empty, text=subtitle, text_color=COLORS['muted']).pack(anchor='w', padx=22, pady=(0, 22))
            return

        for idx, game in enumerate(filtered):
            card = ctk.CTkFrame(holder, fg_color=COLORS['card'], corner_radius=20,
                                border_width=2, border_color=COLORS['black'])
            r, c = divmod(idx, columns)
            card.grid(row=r, column=c, sticky='nsew', padx=gap * 5, pady=gap * 5)
            holder.grid_columnconfigure(c, weight=1, uniform='gamecol')

            art = ctk.CTkLabel(card, text='', fg_color=COLORS['panel2'], corner_radius=18)
            art.pack(fill='x', padx=2, pady=2)
            app.image_loader.request(
                game.banner_url or game.icon_url,
                game.name,
                (430, 220),
                'banner',
                lambda img, w=art: w.configure(image=img, text='')
            )

            body = ctk.CTkFrame(card, fg_color='transparent')
            body.pack(fill='both', expand=True, padx=14, pady=(8, 14))

            top = ctk.CTkFrame(body, fg_color='transparent')
            top.pack(fill='x')
            ctk.CTkLabel(top, text=game.name, font=ctk.CTkFont(size=17, weight='bold'), anchor='w').pack(side='left', fill='x', expand=True)
            if app.manager.update_available(game):
                ctk.CTkLabel(top, text='UPDATE', text_color='#F0C36B',
                             fg_color='#2E2615', corner_radius=8,
                             font=ctk.CTkFont(size=10, weight='bold')).pack(side='right', padx=(8, 0))

            ctk.CTkLabel(body, text=f'v{game.version}  •  {game.category or "Gra"}',
                         text_color=COLORS['muted'], anchor='w').pack(fill='x', pady=(2, 8))
            if game.description:
                ctk.CTkLabel(body, text=game.description, text_color=COLORS['muted'],
                             justify='left', anchor='nw', wraplength=360).pack(fill='x', pady=(0, 8))

            ctk.CTkButton(
                body, text='Szczegóły', height=34, fg_color='transparent',
                hover_color=COLORS['panel2'], border_width=1,
                border_color=COLORS['border_soft'],
                command=lambda g=game: app.open_game_details(g)
            ).pack(fill='x', pady=(0, 6))

            primary_text = _substitute(primary_template.get('text', '{{game.primary_label}}'), _game_context(app, game))
            ctk.CTkButton(
                body, text=primary_text, height=38,
                command=lambda g=game, d=primary_template: perform_action(app, d.get('action', 'game.primary'), g, d),
                **_button_style(primary_template)
            ).pack(fill='x', pady=2)

            if app.manager.is_installed(game):
                ctk.CTkButton(
                    body, text=uninstall_template.get('text', 'Odinstaluj'), height=34,
                    command=lambda g=game, d=uninstall_template: perform_action(app, d.get('action', 'game.uninstall'), g, d),
                    **_button_style(uninstall_template)
                ).pack(fill='x', pady=2)
                ctk.CTkButton(
                    body, text=path_template.get('text', 'Lokalizacja'), height=34,
                    command=lambda g=game, d=path_template: perform_action(app, d.get('action', 'game.path'), g, d),
                    **_button_style(path_template)
                ).pack(fill='x', pady=2)

    if search_enabled:
        search_var.trace_add('write', rebuild)
        entry.bind('<Escape>', lambda _e: search_var.set(''))
        entry.bind('<Return>', lambda _e: None)
    rebuild()
    return wrapper

def build_game_detail(app,parent,el):
    game=app.selected_game
    outer=ctk.CTkFrame(parent,fg_color='transparent')
    if not game:
        ctk.CTkLabel(outer,text='Nie wybrano gry',font=ctk.CTkFont(size=28,weight='bold')).pack(anchor='w',padx=20,pady=20);return outer
    hero=ctk.CTkFrame(outer,fg_color=COLORS['panel'],corner_radius=24,border_width=2,border_color=COLORS['black']);hero.pack(fill='x',pady=3)
    art=ctk.CTkLabel(hero,text='',fg_color=COLORS['panel2'],corner_radius=22);art.pack(fill='x',padx=2,pady=2)
    app.image_loader.request(game.banner_url or game.icon_url,game.name,(1000,320),'hero',lambda img,w=art:w.configure(image=img,text=''))
    box=ctk.CTkFrame(hero,fg_color='transparent');box.place(relx=.035,rely=.08,relwidth=.9,relheight=.82)
    ctk.CTkLabel(box,text=game.name,font=ctk.CTkFont(size=34,weight='bold'),text_color='#FFF',anchor='w').pack(anchor='w')
    ctk.CTkLabel(box,text=f'v{game.version} • {game.developer} • {game.category}',text_color='#D0D0D0').pack(anchor='w',pady=(5,8))
    ctk.CTkLabel(box,text=game.description or '',wraplength=850,justify='left',text_color='#D6D6D6').pack(anchor='w')
    actions=ctk.CTkFrame(outer,fg_color=COLORS['panel'],corner_radius=18,border_width=2,border_color=COLORS['black']);actions.pack(fill='x',pady=8)
    primary=app.layout.get('templates',{}).get(el.get('template_primary','game_primary'),{})
    uninstall=app.layout.get('templates',{}).get(el.get('template_uninstall','game_uninstall'),{})
    path_t=app.layout.get('templates',{}).get(el.get('template_path','game_path'),{})
    ctk.CTkButton(actions,text=_substitute(primary.get('text','{{game.primary_label}}'),_game_context(app,game)),height=44,command=lambda d=primary:perform_action(app,d.get('action','game.primary'),game,d),**_button_style(primary)).pack(side='left',fill='x',expand=True,padx=(14,5),pady=14)
    if app.manager.is_installed(game):
        ctk.CTkButton(actions,text=uninstall.get('text','Odinstaluj'),height=44,command=lambda d=uninstall:perform_action(app,d.get('action','game.uninstall'),game,d),**_button_style(uninstall)).pack(side='left',fill='x',expand=True,padx=5,pady=14)
        ctk.CTkButton(actions,text=path_t.get('text','Lokalizacja'),height=44,command=lambda d=path_t:perform_action(app,d.get('action','game.path'),game,d),**_button_style(path_t)).pack(side='left',fill='x',expand=True,padx=(5,14),pady=14)
    elif game.homepage_url:
        ctk.CTkButton(actions,text='Strona projektu',height=44,command=lambda:perform_action(app,'game.homepage',game),fg_color=COLORS['panel2'],hover_color=COLORS['card_hover'],border_width=1,border_color=COLORS['black']).pack(side='left',fill='x',expand=True,padx=(5,14),pady=14)
    body=ctk.CTkScrollableFrame(outer,fg_color='transparent');body.pack(fill='both',expand=True,pady=4)
    if game.notes:
        card=ctk.CTkFrame(body,fg_color=COLORS['panel'],corner_radius=18,border_width=2,border_color=COLORS['black']);card.pack(fill='x',pady=6)
        ctk.CTkLabel(card,text='NOTATKA DEWELOPERA',font=ctk.CTkFont(size=10,weight='bold'),text_color=COLORS['muted']).pack(anchor='w',padx=18,pady=(16,4));ctk.CTkLabel(card,text=game.notes,justify='left',wraplength=900).pack(anchor='w',padx=18,pady=(0,16))
    info=ctk.CTkFrame(body,fg_color=COLORS['panel'],corner_radius=18,border_width=2,border_color=COLORS['black']);info.pack(fill='x',pady=6)
    ctk.CTkLabel(info,text=f'Instalacja: {app.manager.installs / game.id}',text_color=COLORS['muted']).pack(anchor='w',padx=18,pady=16)
    return outer
