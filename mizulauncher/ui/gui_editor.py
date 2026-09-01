from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ..layout_engine import DEFAULT_LAYOUT, export_layout, import_layout, make_element_id, save_layout
from ..models import Game
from .dialogs import error, info
from .theme import COLORS


ELEMENT_TYPES = [
    ('text', 'Tekst'), ('section_title', 'Tytuł sekcji'), ('button', 'Przycisk'),
    ('image', 'Obraz'), ('separator', 'Separator'), ('spacer', 'Odstęp'),
    ('featured_game', 'Featured Game'), ('game_list', 'Lista gier'), ('game_detail', 'Szczegóły gry'),
]
ACTIONS = [
    ('none', 'Brak'), ('navigate.home', 'Otwórz Home'), ('navigate.library', 'Otwórz Bibliotekę'),
    ('navigate.settings', 'Otwórz Ustawienia'), ('navigate.page', 'Otwórz własną zakładkę'), ('game.details', 'Szczegóły gry'),
    ('game.primary', 'Gra / Pobierz'), ('game.play', 'Graj'), ('game.install', 'Zainstaluj'),
    ('game.uninstall', 'Odinstaluj'), ('game.path', 'Lokalizacja gry'), ('game.homepage', 'Strona projektu'),
    ('refresh', 'Odśwież katalog'), ('account', 'Account Manager'), ('open_url', 'Otwórz URL'),
]


class GuiEditor(ctk.CTkToplevel):
    def __init__(self, master, layout: dict, games: list[Game], on_save=None, on_publish=None):
        super().__init__(master)
        self.master_app = master
        self.layout = deepcopy(layout)
        self.games = games
        self.on_save = on_save
        self.on_publish = on_publish
        self.current_page = 'home'
        self.selected_index = 0
        self.template_mode = False
        self.title('MizuLauncher • GUI Editor')
        self.geometry('1500x900')
        self.minsize(1200, 760)
        self.transient(master)

        self._build()
        self._refresh_element_list()
        self._refresh_canvas()
        self._select_element(0)

    def _build(self):
        self.top = ctk.CTkFrame(self, height=58, fg_color=COLORS['panel'], corner_radius=0, border_width=1, border_color=COLORS['black'])
        self.top.pack(fill='x')
        self.top.pack_propagate(False)
        ctk.CTkLabel(self.top, text='GUI EDITOR', font=ctk.CTkFont(size=21, weight='bold')).pack(side='left', padx=20)
        ctk.CTkButton(self.top, text='↶ Reset', width=80, command=self._reset).pack(side='right', padx=(5, 12), pady=10)
        ctk.CTkButton(self.top, text='Import', width=82, command=self._import).pack(side='right', padx=5, pady=10)
        ctk.CTkButton(self.top, text='Export', width=82, command=self._export).pack(side='right', padx=5, pady=10)
        ctk.CTkButton(self.top, text='Publikuj', width=94, fg_color=COLORS['text'], text_color=COLORS['black'], hover_color=COLORS['white'], command=self._publish).pack(side='right', padx=5, pady=10)
        ctk.CTkButton(self.top, text='Zapisz', width=82, fg_color=COLORS['panel3'], command=self._save).pack(side='right', padx=5, pady=10)

        self.body = ctk.CTkFrame(self, fg_color=COLORS['bg'], corner_radius=0)
        self.body.pack(fill='both', expand=True)

        self.left = ctk.CTkFrame(self.body, width=250, fg_color=COLORS['panel'], corner_radius=0, border_width=1, border_color=COLORS['black'])
        self.left.pack(side='left', fill='y')
        self.left.pack_propagate(False)
        self.mid = ctk.CTkFrame(self.body, fg_color=COLORS['bg2'], corner_radius=0)
        self.mid.pack(side='left', fill='both', expand=True)
        self.right = ctk.CTkScrollableFrame(self.body, width=335, fg_color=COLORS['panel'], corner_radius=0, border_width=1, border_color=COLORS['black'])
        self.right.pack(side='right', fill='y')

        ctk.CTkLabel(self.left, text='STRONY', font=ctk.CTkFont(size=11, weight='bold'), text_color=COLORS['muted']).pack(anchor='w', padx=16, pady=(18, 8))
        self.page_var = ctk.StringVar(value='home')
        self.page_combo = ctk.CTkComboBox(self.left, values=[], variable=self.page_var, command=self._change_page, height=40)
        self.page_combo.pack(fill='x', padx=14)
        ctk.CTkButton(self.left, text='+ Nowa zakładka', height=38, fg_color=COLORS['panel2'], hover_color=COLORS['card_hover'], command=self._new_page).pack(fill='x', padx=14, pady=7)
        ctk.CTkButton(self.left, text='− Usuń zakładkę', height=34, fg_color=COLORS['red_soft'], hover_color=COLORS['red'], command=self._delete_page).pack(fill='x', padx=14, pady=(0, 14))

        ctk.CTkFrame(self.left, height=2, fg_color=COLORS['black']).pack(fill='x', padx=14, pady=6)
        ctk.CTkLabel(self.left, text='ELEMENTY', font=ctk.CTkFont(size=11, weight='bold'), text_color=COLORS['muted']).pack(anchor='w', padx=16, pady=(10, 5))
        self.element_list = tk.Listbox(self.left, bg='#101010', fg='#E8E8E8', selectbackground='#303030', selectforeground='#FFFFFF', relief='flat', highlightthickness=0, activestyle='none')
        self.element_list.pack(fill='both', expand=True, padx=14, pady=4)
        self.element_list.bind('<<ListboxSelect>>', lambda _e: self._select_element_from_list())
        for txt, typ in ELEMENT_TYPES:
            ctk.CTkButton(self.left, text=f'+ {typ}', height=28, fg_color='transparent', hover_color=COLORS['panel2'], anchor='w', command=lambda t=txt: self._add_element(t)).pack(fill='x', padx=14, pady=1)
        row = ctk.CTkFrame(self.left, fg_color='transparent'); row.pack(fill='x', padx=14, pady=10)
        ctk.CTkButton(row, text='↑', width=42, command=lambda: self._move(-1)).pack(side='left', padx=(0, 4))
        ctk.CTkButton(row, text='↓', width=42, command=lambda: self._move(1)).pack(side='left', padx=4)
        ctk.CTkButton(row, text='Kopiuj', width=70, command=self._duplicate).pack(side='left', padx=4)
        ctk.CTkButton(row, text='Usuń', width=60, fg_color=COLORS['red_soft'], hover_color=COLORS['red'], command=self._delete_element).pack(side='left', padx=4)

        # Canvas area
        ctk.CTkLabel(self.mid, text='PODGLĄD / LIVE CANVAS', font=ctk.CTkFont(size=11, weight='bold'), text_color=COLORS['muted']).pack(anchor='w', padx=18, pady=(14, 6))
        self.canvas_wrap = ctk.CTkFrame(self.mid, fg_color=COLORS['black'], corner_radius=18, border_width=2, border_color=COLORS['black'])
        self.canvas_wrap.pack(fill='both', expand=True, padx=18, pady=(0, 10))
        self.canvas = ctk.CTkFrame(self.canvas_wrap, fg_color='#090909', corner_radius=14)
        self.canvas.place(relx=.02, rely=.03, relwidth=.96, relheight=.94)
        self.canvas.bind('<Configure>', lambda _e: self._refresh_canvas())
        ctk.CTkLabel(self.mid, text='Kliknij element na liście, aby edytować. Właściwości działają na żywo.', text_color=COLORS['subtle']).pack(anchor='w', padx=18, pady=(0, 8))

        # Property panel
        self.prop_title = ctk.CTkLabel(self.right, text='Właściwości', font=ctk.CTkFont(size=21, weight='bold'))
        self.prop_title.pack(anchor='w', padx=18, pady=(18, 12))
        self.prop_frame = ctk.CTkFrame(self.right, fg_color='transparent')
        self.prop_frame.pack(fill='x', padx=12)
        self._refresh_page_combo()

    def _page(self):
        return self.layout['pages'][self.current_page]

    def _elements(self):
        return self._page().setdefault('elements', [])

    def _refresh_page_combo(self):
        vals = list(self.layout['pages'].keys())
        self.page_combo.configure(values=vals)
        if self.current_page not in vals:
            self.current_page = vals[0]
        self.page_var.set(self.current_page)

    def _change_page(self, value):
        self.current_page = value
        self.selected_index = 0
        self._refresh_element_list(); self._refresh_canvas(); self._refresh_properties()

    def _new_page(self):
        dlg = ctk.CTkInputDialog(text='Nazwa nowej zakładki:', title='Nowa zakładka')
        name = (dlg.get_input() or '').strip().lower().replace(' ', '_')
        if not name or name in self.layout['pages']:
            return
        self.layout['pages'][name] = {'label': name.title(), 'elements': []}
        self.current_page = name
        self._refresh_page_combo(); self._refresh_element_list(); self._refresh_canvas(); self._refresh_properties()

    def _delete_page(self):
        if len(self.layout['pages']) <= 1:
            return
        self.layout['pages'].pop(self.current_page, None)
        self.current_page = next(iter(self.layout['pages']))
        self._refresh_page_combo(); self._refresh_element_list(); self._refresh_canvas(); self._refresh_properties()

    def _refresh_element_list(self):
        self.element_list.delete(0, 'end')
        for el in self._elements():
            self.element_list.insert('end', f"{el.get('type','element')}   •   {el.get('id','')}")
        if self._elements():
            self.selected_index = max(0, min(self.selected_index, len(self._elements()) - 1))
            self.element_list.selection_set(self.selected_index)

    def _select_element_from_list(self):
        sel = self.element_list.curselection()
        if sel:
            self._select_element(sel[0])

    def _select_element(self, index):
        els = self._elements()
        if not els:
            self.selected_index = -1
            self._refresh_properties(); self._refresh_canvas(); return
        self.selected_index = max(0, min(index, len(els) - 1))
        try: self.element_list.selection_clear(0, 'end'); self.element_list.selection_set(self.selected_index); self.element_list.activate(self.selected_index)
        except Exception: pass
        self._refresh_properties(); self._refresh_canvas()

    def _selected(self):
        els = self._elements()
        return els[self.selected_index] if 0 <= self.selected_index < len(els) else None

    def _refresh_properties(self):
        for c in self.prop_frame.winfo_children(): c.destroy()
        self._property_widgets = []
        el = self._selected()
        if not el:
            ctk.CTkLabel(self.prop_frame, text='Wybierz element.').pack(anchor='w', pady=8)
            return
        self._prop_entry('ID', 'id', el.get('id',''), readonly=True)
        self._prop_combo('Typ', 'type', el.get('type','text'), [x[0] for x in ELEMENT_TYPES])
        self._prop_entry('Tekst', 'text', el.get('text',''))
        for key, label in [('x','X %'), ('y','Y %'), ('w','Szerokość %'), ('h','Wysokość %'), ('font_size','Rozmiar tekstu'), ('radius','Zaokrąglenie'), ('border_width','Obramowanie'), ('opacity','Przezroczystość')]:
            if key in el or key in {'x','y','w','h'}:
                self._prop_entry(label, key, str(el.get(key, 0)))
        self._prop_entry('Kolor tła', 'fg', el.get('fg',''))
        self._prop_entry('Kolor tekstu', 'text_color', el.get('text_color',''))
        self._prop_entry('Hover', 'hover', el.get('hover',''))
        self._prop_entry('Obraz / URL', 'image_url', el.get('image_url',''))
        self._prop_entry('URL', 'url', el.get('url',''))
        if el.get('type') == 'button':
            self._prop_combo('Funkcja', 'action', el.get('action','none'), [x[0] for x in ACTIONS])
            self._prop_combo('Zakładka', 'target_page', el.get('target_page','home'), list(self.layout.get('pages', {}).keys()))
            self._prop_combo('Gra', 'game_binding', el.get('game_binding','context'), ['context','selected','fixed'])
            self._prop_combo('Template', 'template_id', el.get('template_id',''), [''] + list(self.layout.get('templates', {}).keys()))
            self._prop_entry('ID stałej gry', 'game_id', el.get('game_id',''))
        if el.get('type') in {'game_list','featured_game','game_detail'}:
            self._prop_combo('Przycisk główny', 'template_primary', el.get('template_primary','game_primary'), list(self.layout.get('templates', {}).keys()))
            self._prop_combo('Odinstaluj', 'template_uninstall', el.get('template_uninstall','game_uninstall'), list(self.layout.get('templates', {}).keys()))
            self._prop_combo('Lokalizacja', 'template_path', el.get('template_path','game_path'), list(self.layout.get('templates', {}).keys()))
            if el.get('type') == 'game_list':
                self._prop_entry('Kolumny', 'columns', str(el.get('columns',3)))
                self._prop_entry('Szer. karty %', 'card_w', str(el.get('card_w',30)))
                self._prop_entry('Gap', 'gap', str(el.get('gap',1.2)))
        if el.get('type') == 'image':
            self._prop_entry('Fit', 'fit', el.get('fit','cover'))

        ctk.CTkButton(self.prop_frame, text='Zapisz właściwości', height=42, fg_color=COLORS['text'], text_color=COLORS['black'], hover_color=COLORS['white'], command=self._commit_property_changes).pack(fill='x', pady=(14,8))
        ctk.CTkButton(self.prop_frame, text='Edytor templatek przycisków', height=38, fg_color=COLORS['panel2'], command=self._open_template_editor).pack(fill='x', pady=4)

    def _prop_entry(self, label, key, value, readonly=False):
        frame=ctk.CTkFrame(self.prop_frame, fg_color='transparent'); frame.pack(fill='x', pady=3)
        ctk.CTkLabel(frame, text=label, text_color=COLORS['muted']).pack(anchor='w')
        e=ctk.CTkEntry(frame, height=34)
        e.pack(fill='x')
        e.insert(0,str(value))
        if readonly: e.configure(state='disabled')
        frame._field=(key,e)
        self._property_widgets.append(frame) if hasattr(self,'_property_widgets') else None
        if not hasattr(self,'_property_widgets'): self._property_widgets=[]
        self._property_widgets.append(frame)

    def _prop_combo(self, label, key, value, values):
        frame=ctk.CTkFrame(self.prop_frame, fg_color='transparent'); frame.pack(fill='x', pady=3)
        ctk.CTkLabel(frame, text=label, text_color=COLORS['muted']).pack(anchor='w')
        v=ctk.StringVar(value=str(value)); c=ctk.CTkComboBox(frame, values=[str(x) for x in values], variable=v, height=34)
        c.pack(fill='x'); frame._field=(key,c); frame._var=v
        if not hasattr(self,'_property_widgets'): self._property_widgets=[]
        self._property_widgets.append(frame)

    def _commit_property_changes(self):
        el=self._selected()
        if not el: return
        for frame in getattr(self,'_property_widgets',[]):
            if not frame.winfo_exists(): continue
            key, widget=frame._field
            if isinstance(widget, ctk.CTkEntry):
                value=widget.get().strip()
            else:
                value=widget.get().strip()
            if key in {'x','y','w','h','font_size','radius','border_width','opacity','columns','card_w','gap'}:
                try: value=float(value)
                except ValueError: continue
                if key in {'columns'}: value=int(value)
            el[key]=value
        self._property_widgets=[]
        self._refresh_element_list(); self._refresh_canvas(); self._refresh_properties()

    def _add_element(self, typ):
        els=self._elements(); eid=make_element_id(typ,els)
        el={'id':eid,'type':typ,'x':8,'y':8,'w':40,'h':10,'radius':12,'font_size':16,'fg':COLORS['panel2'],'text_color':COLORS['text'],'hover':COLORS['card_hover']}
        if typ == 'text': el['text']='Nowy tekst'
        elif typ == 'section_title': el.update(text='Nowa sekcja', font_size=24, w=50, h=7)
        elif typ == 'button': el.update(text='Przycisk', action='none', game_binding='context', w=24, h=6)
        elif typ == 'image': el.update(image_url='', w=35, h=25)
        elif typ == 'separator': el.update(fg=COLORS['black'], h=0.5, w=80)
        elif typ == 'spacer': el.update(w=20, h=5)
        elif typ == 'featured_game': el.update(w=94, h=45)
        elif typ == 'game_list': el.update(w=94, h=40, columns=3, card_w=30, show_actions=True, template_primary='game_primary', template_uninstall='game_uninstall', template_path='game_path')
        elif typ == 'game_detail': el.update(w=94, h=90, template_primary='game_primary', template_uninstall='game_uninstall', template_path='game_path')
        els.append(el); self.selected_index=len(els)-1
        self._refresh_element_list(); self._select_element(self.selected_index)

    def _move(self, delta):
        els=self._elements(); i=self.selected_index; j=i+delta
        if not (0<=i<len(els) and 0<=j<len(els)): return
        els[i],els[j]=els[j],els[i]; self.selected_index=j; self._refresh_element_list(); self._select_element(j)

    def _duplicate(self):
        el=self._selected()
        if not el: return
        copy=deepcopy(el); copy['id']=make_element_id(copy.get('type','element'),self._elements()); copy['x']=min(90,float(copy.get('x',0))+2); copy['y']=min(90,float(copy.get('y',0))+2)
        self._elements().insert(self.selected_index+1,copy); self.selected_index+=1; self._refresh_element_list(); self._select_element(self.selected_index)

    def _delete_element(self):
        if self.selected_index<0: return
        els=self._elements()
        if 0<=self.selected_index<len(els): els.pop(self.selected_index)
        self.selected_index=max(0,self.selected_index-1); self._refresh_element_list(); self._refresh_properties(); self._refresh_canvas()

    def _refresh_canvas(self):
        if not self.canvas.winfo_exists(): return
        for c in self.canvas.winfo_children(): c.destroy()
        for idx, el in enumerate(self._elements()):
            self._render_canvas_element(el, idx)

    def _render_canvas_element(self, el, idx):
        x=float(el.get('x',2))/100; y=float(el.get('y',2))/100; w=float(el.get('w',20))/100; h=float(el.get('h',10))/100
        typ=el.get('type','text'); selected=idx==self.selected_index
        bg=el.get('fg','transparent') if typ not in {'separator','spacer'} else (el.get('fg',COLORS['black']) if typ=='separator' else 'transparent')
        if typ in {'text','section_title'}:
            wgt=ctk.CTkLabel(self.canvas,text=el.get('text','Text'),fg_color=bg, text_color=el.get('text_color',COLORS['text']),font=ctk.CTkFont(size=int(float(el.get('font_size',16))),weight='bold' if typ=='section_title' else 'normal'),anchor='w')
        elif typ=='image':
            wgt=ctk.CTkLabel(self.canvas,text='IMAGE',fg_color=COLORS['panel2'],text_color=COLORS['muted'])
            url=el.get('image_url','')
            if url and hasattr(self.master_app,'image_loader'):
                self.master_app.image_loader.request(url,'Preview',(max(40,int(self.canvas.winfo_width()*w)),max(40,int(self.canvas.winfo_height()*h))),'banner',lambda img,w=wgt:w.configure(image=img,text=''))
        elif typ=='button':
            wgt=ctk.CTkButton(self.canvas,text=el.get('text','Przycisk'),fg_color=bg,hover_color=el.get('hover',COLORS['card_hover']),text_color=el.get('text_color',COLORS['text']),corner_radius=int(float(el.get('radius',12))),border_width=int(float(el.get('border_width',1))),border_color=el.get('border_color',COLORS['black']),command=lambda: self._test_action(el))
        elif typ=='separator':
            wgt=ctk.CTkFrame(self.canvas,fg_color=bg,corner_radius=0)
        elif typ=='spacer':
            wgt=ctk.CTkFrame(self.canvas,fg_color='transparent')
        elif typ in {'featured_game','game_list','game_detail'}:
            wgt=ctk.CTkFrame(self.canvas,fg_color=COLORS['panel'],corner_radius=int(float(el.get('radius',16))),border_width=2 if selected else 1,border_color=COLORS['white'] if selected else COLORS['black'])
            label='FEATURED GAME' if typ=='featured_game' else ('GAME LIST' if typ=='game_list' else 'GAME DETAILS')
            ctk.CTkLabel(wgt,text=label,font=ctk.CTkFont(size=14,weight='bold'),text_color=COLORS['text']).pack(anchor='w',padx=16,pady=(14,4))
            ctk.CTkLabel(wgt,text=self.games[0].name if self.games else 'Przykładowa gra',text_color=COLORS['muted']).pack(anchor='w',padx=16)
            if typ in {'game_list','game_detail'}:
                ctk.CTkButton(wgt,text='Graj / Pobierz',height=32,fg_color=COLORS['text'],text_color=COLORS['black'],command=lambda: self._test_game_action('game.primary')).pack(anchor='w',padx=16,pady=10)
        else:
            wgt=ctk.CTkFrame(self.canvas,fg_color=bg,corner_radius=10)
        if selected:
            try: wgt.configure(border_width=max(2,int(float(el.get('border_width',2)))), border_color=COLORS['white'])
            except Exception: pass
        wgt.place(relx=x,rely=y,relwidth=max(.01,w),relheight=max(.005,h))
        wgt.bind('<Button-1>',lambda _e,i=idx:self._select_element(i))
        for ch in wgt.winfo_children(): ch.bind('<Button-1>',lambda _e,i=idx:self._select_element(i))

    def _test_action(self, el):
        self._test_game_action(el.get('action','none'), el)

    def _test_game_action(self, action, el=None):
        game=self.games[0] if self.games else None
        if not game:
            info(self,'Podgląd','Dodaj przynajmniej jedną grę, aby testować akcje.')
            return
        app=self.master_app
        try:
            if action == 'game.primary': app.install_or_launch(game, True)
            elif action == 'game.play': app.manager.launch(game)
            elif action == 'game.install': app.install_or_launch(game, True)
            elif action == 'game.uninstall': app.uninstall_game(game)
            elif action == 'game.path': app.open_game_location(game)
            elif action == 'game.homepage': app.open_game_homepage(game)
            elif action == 'game.details': app.open_game_details(game)
            elif action == 'navigate.home': app.show_view('home')
            elif action == 'navigate.library': app.show_view('library')
            elif action == 'navigate.settings': app.show_view('settings')
            elif action == 'account': app.open_account_manager()
            elif action == 'refresh': app.refresh_games()
            elif action == 'open_url' and el and el.get('url'):
                import webbrowser; webbrowser.open(el['url'])
        except Exception as exc:
            error(self,'Akcja testowa nieudana',str(exc))

    def _open_template_editor(self):
        win=ctk.CTkToplevel(self); win.title('Button Templates'); win.geometry('700x680'); win.transient(self)
        left=ctk.CTkFrame(win,width=210,fg_color=COLORS['panel']); left.pack(side='left',fill='y'); left.pack_propagate(False)
        right=ctk.CTkScrollableFrame(win,fg_color=COLORS['bg']); right.pack(side='right',fill='both',expand=True)
        names=list(self.layout.setdefault('templates',{}).keys()); var=ctk.StringVar(value=names[0] if names else '')
        listbox=tk.Listbox(left,bg='#101010',fg='#E8E8E8',selectbackground='#303030',relief='flat',highlightthickness=0); listbox.pack(fill='both',expand=True,padx=14,pady=14)
        for n in names:listbox.insert('end',n)
        fields={}
        def draw(name):
            for c in right.winfo_children():c.destroy()
            fields.clear(); t=self.layout['templates'].setdefault(name,{})
            ctk.CTkLabel(right,text=name,font=ctk.CTkFont(size=24,weight='bold')).pack(anchor='w',padx=16,pady=(18,10))
            for key,label in [('text','Tekst'),('fg','Tło'),('text_color','Tekst'),('hover','Hover'),('border_color','Obramowanie'),('radius','Radius'),('height','Wysokość'),('font_size','Font size')]:
                ctk.CTkLabel(right,text=label,text_color=COLORS['muted']).pack(anchor='w',padx=16,pady=(6,3)); e=ctk.CTkEntry(right,height=36);e.pack(fill='x',padx=16);e.insert(0,str(t.get(key,'')));fields[key]=e
            ctk.CTkLabel(right,text='Funkcja',text_color=COLORS['muted']).pack(anchor='w',padx=16,pady=(8,3)); action=ctk.CTkComboBox(right,values=[x[0] for x in ACTIONS],height=36);action.pack(fill='x',padx=16);action.set(t.get('action','game.primary'));fields['action']=action
            def save_t():
                for k,w in fields.items(): t[k]=w.get().strip()
                try:
                    t['radius']=float(t.get('radius',12));t['height']=float(t.get('height',42));t['font_size']=float(t.get('font_size',13))
                except: pass
                self._refresh_canvas(); info(win,'Zapisano','Template przycisku zapisany.')
            ctk.CTkButton(right,text='Zapisz template',height=42,fg_color=COLORS['text'],text_color=COLORS['black'],command=save_t).pack(fill='x',padx=16,pady=20)
        def select(_=None):
            s=listbox.curselection()
            if s: draw(listbox.get(s[0]))
        listbox.bind('<<ListboxSelect>>',select)
        if names:listbox.selection_set(0);draw(names[0])
        ctk.CTkButton(left,text='+ Nowy template',height=38,command=lambda:self._new_template(listbox,draw)).pack(fill='x',padx=14,pady=(0,8))
        ctk.CTkButton(left,text='Zamknij',height=36,command=win.destroy).pack(fill='x',padx=14,pady=(0,14))

    def _new_template(self,listbox,draw):
        dlg=ctk.CTkInputDialog(text='ID template:',title='Nowy template'); name=(dlg.get_input() or '').strip().lower().replace(' ','_')
        if not name:return
        self.layout.setdefault('templates',{})[name]=deepcopy(DEFAULT_LAYOUT['templates']['game_primary']);listbox.insert('end',name);listbox.selection_clear(0,'end');listbox.selection_set('end');draw(name)

    def _save(self):
        save_layout(self.layout)
        if self.on_save:self.on_save(self.layout)
        info(self,'Zapisano','Layout zapisano lokalnie. Nie zapomnij opublikować go, jeśli ma być widoczny dla innych.')

    def _publish(self):
        self._save()
        if self.on_publish:self.on_publish(self.layout)

    def _export(self):
        p=filedialog.asksaveasfilename(title='Eksport layoutu',defaultextension='.json',filetypes=[('JSON','*.json')])
        if p:
            try: export_layout(self.layout,p); info(self,'Eksport','Layout zapisany.')
            except Exception as exc:error(self,'Eksport nieudany',str(exc))

    def _import(self):
        p=filedialog.askopenfilename(title='Import layoutu',filetypes=[('JSON','*.json')])
        if p:
            try:
                self.layout=import_layout(p);self._refresh_page_combo();self._refresh_element_list();self._refresh_canvas();self._refresh_properties();info(self,'Import','Layout wczytany. Kliknij Zapisz, aby go zachować.')
            except Exception as exc:error(self,'Import nieudany',str(exc))

    def _reset(self):
        self.layout=deepcopy(DEFAULT_LAYOUT);self.current_page='home';self._refresh_page_combo();self._refresh_element_list();self._refresh_canvas();self._refresh_properties()
