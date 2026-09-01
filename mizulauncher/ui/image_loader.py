from __future__ import annotations

import hashlib
import io
import re
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse

import customtkinter as ctk
import requests
from PIL import Image, ImageDraw, ImageOps, ImageFilter


class ImageLoader:
    def __init__(self, root, cache_dir: Path | None = None):
        self.root = root
        self.cache_dir = cache_dir or (Path.home() / ".mizulauncher" / "images")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory = {}
        self.active = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36 MizuLauncher/3.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        })

    @staticmethod
    def _key(url, kind, size):
        return hashlib.sha256(f"{kind}|{size}|{url}".encode()).hexdigest()

    def _fallback(self, text, size, kind):
        w,h=size
        image=Image.new("RGB",size,"#161616"); draw=ImageDraw.Draw(image)
        for y in range(h):
            shade=19+int(19*y/max(1,h-1)); draw.line((0,y,w,y),fill=(shade,shade,shade))
        initials="".join(p[:1] for p in text.split()[:2]).upper() or "MZ"
        if kind == "banner":
            glow=Image.new("RGBA",size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
            gd.ellipse((w*0.55,h*0.08,w*1.1,h*0.95),fill=(255,255,255,18)); glow=glow.filter(ImageFilter.GaussianBlur(28))
            image=Image.alpha_composite(image.convert("RGBA"),glow).convert("RGB"); draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((2,2,w-3,h-3),radius=max(8,min(size)//10),outline=(0,0,0),width=5)
        draw.text((w//2,h//2),initials,anchor="mm",fill="#E8E8E8")
        return image

    @staticmethod
    def _fit(image,size,kind):
        return ImageOps.fit(image.convert("RGB"),size,method=Image.Resampling.LANCZOS,centering=(0.5,0.42 if kind in {"banner","hero"} else 0.5))

    @staticmethod
    def _hero_overlay(image):
        # 70% black glass/gradient over the left side, baked into pixels so Tk does not need alpha frames.
        img=image.convert("RGBA"); w,h=img.size; overlay=Image.new("RGBA",(w,h),(0,0,0,0)); d=ImageDraw.Draw(overlay)
        for x in range(w):
            p=x/w
            if p<0.62:
                alpha=int(178*(1-p/0.78)) if p<0.78 else 0
                alpha=max(0,min(178,alpha)); d.line((x,0,x,h),fill=(0,0,0,alpha))
        return Image.alpha_composite(img,overlay).convert("RGB")

    def _resolve_html_image(self, html, base_url):
        patterns=[r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']']
        for p in patterns:
            m=re.search(p,html,re.I)
            if m:
                return urljoin(base_url,m.group(1))
        return None

    def _normalize_url(self,url):
        p=urlparse(url)
        host=p.netloc.lower()
        # GitHub blob -> raw
        if host == "github.com" and "/blob/" in p.path:
            return "https://raw.githubusercontent.com"+p.path.replace("/blob/","/",1)
        return url

    def _download_bytes(self,url):
        url=self._normalize_url(url.strip())
        p=urlparse(url)
        if p.scheme not in {"http","https"}: raise ValueError("URL musi zaczynać się od http:// albo https://")
        r=self.session.get(url,timeout=(10,25),allow_redirects=True)
        r.raise_for_status()
        ct=(r.headers.get("Content-Type") or "").lower()
        raw=r.content
        if "text/html" in ct:
            resolved=self._resolve_html_image(r.text,r.url)
            if not resolved: raise ValueError("URL prowadzi do strony, nie bezpośrednio do obrazu.")
            r2=self.session.get(resolved,timeout=(10,25),allow_redirects=True); r2.raise_for_status(); raw=r2.content
        if not raw: raise ValueError("Serwer zwrócił pusty obraz.")
        return raw

    def _load_pil(self,url,size,kind,name):
        key=self._key(url,kind,size); path=self.cache_dir/f"{key}.bin"
        raw=path.read_bytes() if path.exists() else None
        if raw is None:
            raw=self._download_bytes(url)
            try:path.write_bytes(raw)
            except OSError:pass
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.load(); img=self._fit(source,size,kind)
                if kind == "hero": img=self._hero_overlay(img)
                return img
        except Exception as exc:
            raise ValueError(f"Nie udało się odczytać obrazu: {exc}") from exc

    def request(self,url,name,size,kind,callback):
        url=(url or "").strip()
        if not url:
            pil=self._fallback(name,size,kind); callback(ctk.CTkImage(light_image=pil,dark_image=pil,size=size)); return
        key=(url,kind,size)
        if key in self.memory: callback(self.memory[key]); return
        job=self._key(url,kind,size)
        if job in self.active:return
        self.active.add(job)
        def worker():
            try: pil=self._load_pil(url,size,kind,name)
            except Exception: pil=self._fallback(name,size,kind)
            def apply():
                self.active.discard(job); img=ctk.CTkImage(light_image=pil,dark_image=pil,size=size); self.memory[key]=img; callback(img)
            self.root.after(0,apply)
        threading.Thread(target=worker,daemon=True).start()
