import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Event
import queue
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import sys
from io import StringIO
import shutil


# ============================================================================
# KONFIGURACJA
# ============================================================================
class Config:
    """Konfiguracja crawlera"""
    def __init__(self, url=None, max_pages=1000, max_workers=10, delay=0.3):
        self.url = url
        self.max_pages = max(1, max_pages)
        self.max_workers = max(1, min(50, max_workers))
        self.delay = max(0.3, delay)
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    def normalize_url(self):
        if self.url and not self.url.startswith(('http://', 'https://')):
            self.url = 'https://' + self.url


# ============================================================================
# DOMENY
# ============================================================================
class DomainManager:
    """Zarządza domenami"""
    def __init__(self, url):
        domain = urlparse(url).netloc
        if domain.startswith('www.'):
            self.allowed = [domain, domain[4:]]
        else:
            self.allowed = [domain, 'www.' + domain]
    
    def is_allowed(self, domain):
        return domain in self.allowed


# ============================================================================
# PARSER HTML
# ============================================================================
class HTMLParser:
    """Parsuje HTML"""
    SKIP = {'mailto:', 'tel:', 'javascript:', '#'}
    BINARY = {'.pdf', '.jpg', '.png', '.zip', '.doc', '.docx', '.xls', '.xlsx', 
              '.gif', '.jpeg', '.svg', '.mp4', '.avi', '.mp3'}
    
    def __init__(self, domain_manager):
        self.dm = domain_manager
    
    def parse(self, url, html):
        """Zwraca (links[], errors[], text)"""
        soup = BeautifulSoup(html, 'html.parser')
        links, errors = self._extract_links(url, soup)
        text = self._extract_text(soup)
        return links, errors, text
    
    def _extract_links(self, source_url, soup):
        links, errors = [], []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            if any(href.startswith(p) for p in self.SKIP):
                continue
            
            try:
                full = urljoin(source_url, href)
                parsed = urlparse(full)
                
                is_internal = self.dm.is_allowed(parsed.netloc) or parsed.netloc == ''
                
                if not parsed.scheme or not parsed.netloc:
                    if is_internal or href.startswith(('/', './', '../', 'wp-content', 'uploads')):
                        errors.append(f"{href} | Niepoprawny URL (brak schematu/domeny) | Źródło: {source_url}")
                    continue
                
                if not self.dm.is_allowed(parsed.netloc):
                    continue
                
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                
                if any(clean.lower().endswith(ext) for ext in self.BINARY):
                    continue
                
                links.append(clean)
            except Exception as e:
                errors.append(f"{href} | Błąd parsowania linku: {type(e).__name__}: {e} | Źródło: {source_url}")
        
        return links, errors
    
    def _extract_text(self, soup):
        for tag in ['script', 'style', 'head', 'title', 'meta', 'iframe', 'noscript']:
            for el in soup.find_all(tag):
                el.extract()
        
        for br in soup.find_all('br'):
            br.replace_with('\n')
        for p in soup.find_all('p'):
            p.append(soup.new_string('\n\n'))
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            h.append(soup.new_string('\n\n'))
        for li in soup.find_all('li'):
            li.insert(0, soup.new_string('• '))
            li.append(soup.new_string('\n'))
        
        text = soup.get_text()
        lines = [l.strip() for l in text.split('\n')]
        text = '\n'.join(l for l in lines if l)
        
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        
        return text.strip()


# ============================================================================
# HTTP CLIENT
# ============================================================================
class HTTPClient:
    """Pobiera strony"""
    def __init__(self, config, stop_event=None):
        self.config = config
        self.stop_event = stop_event
    
    def fetch(self, url):
        """Zwraca (success: bool, content: str, error_msg: str|None)"""
        if self.stop_event and self.stop_event.is_set():
            return False, None, "Przerwano przez użytkownika"
        
        time.sleep(self.config.delay)
        
        try:
            r = requests.get(url, timeout=15, headers=self.config.headers)
            r.raise_for_status()
            
            content_type = r.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return False, None, f"Nie-HTML (Content-Type: {content_type})"
            
            return True, r.text, None
        except requests.exceptions.RequestException as e:
            return False, None, f"{type(e).__name__}: {e}"


# ============================================================================
# STORAGE
# ============================================================================
class Storage:
    """Zapisuje pliki"""
    SEP = "_" * 80
    
    def __init__(self):
        self.lock = Lock()
        self.texts_f = open("teksty.txt", 'w', encoding='utf-8')
        self.links_f = open("all_links.txt", 'w', encoding='utf-8')
    
    def save_page(self, url, text):
        with self.lock:
            try:
                self.texts_f.write(f"{url}\n\n{text}\n\n{self.SEP}\n\n")
                self.texts_f.flush()
                self.links_f.write(f"{url}\n")
                self.links_f.flush()
                return True
            except Exception as e:
                print(f"   ⚠️  Błąd zapisu: {e}")
                return False
    
    def save_errors(self, errors):
        if errors:
            try:
                with open("error_links.txt", 'w', encoding='utf-8') as f:
                    for e in sorted(errors):
                        f.write(e + '\n')
            except Exception as ex:
                print(f"⚠️  Błąd zapisu errorów: {ex}")
    
    def close(self):
        self.texts_f.close()
        self.links_f.close()
    
    def get_file_size_mb(self, filename):
        try:
            return os.path.getsize(filename) / (1024 * 1024)
        except:
            return 0


# ============================================================================
# STATYSTYKI
# ============================================================================
class Stats:
    """Statystyki"""
    def __init__(self):
        self.visited = set()
        self.queued = set()
        self.errors = []
        self.lock = Lock()
        self.start = time.time()
    
    def mark_visited(self, url):
        with self.lock:
            if url in self.visited:
                return False
            self.visited.add(url)
            return True
    
    def add_queued(self, urls):
        added = []
        with self.lock:
            for url in urls:
                if url not in self.visited and url not in self.queued:
                    self.queued.add(url)
                    added.append(url)
        return added
    
    def add_errors(self, errors):
        with self.lock:
            self.errors.extend(errors)
    
    def add_error(self, error):
        with self.lock:
            self.errors.append(error)
    
    def get_counts(self):
        with self.lock:
            return len(self.visited), len(self.queued), len(self.errors)
    
    def get_elapsed_time(self):
        return time.time() - self.start
    
    def get_errors(self):
        with self.lock:
            return self.errors.copy()


# ============================================================================
# CRAWLER
# ============================================================================
class Crawler:
    """Główny crawler"""
    def __init__(self, config, stop_event=None):
        self.config = config
        self.stop_event = stop_event
        
        self.dm = DomainManager(config.url)
        self.http = HTTPClient(config, stop_event)
        self.parser = HTMLParser(self.dm)
        self.storage = Storage()
        self.stats = Stats()
        
        self.queue = queue.Queue()
        self.queue.put(config.url)
        self.stats.add_queued([config.url])
    
    def run(self):
        """Uruchamia crawling"""
        print(f"\n🚀 Start: {self.config.url}")
        print(f"📍 Domeny: {', '.join(self.dm.allowed)}")
        print(f"🔧 Wątków: {self.config.max_workers}")
        print(f"📊 Limit: {self.config.max_pages}")
        print(f"⏱️  Opóźnienie: {self.config.delay}s\n")
        
        try:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = {}
                
                while True:
                    if self.stop_event and self.stop_event.is_set():
                        print("\n⚠️  Przerwano przez użytkownika")
                        break
                    
                    visited, _, _ = self.stats.get_counts()
                    if visited >= self.config.max_pages:
                        print(f"\n⚠️  Osiągnięto limit {self.config.max_pages} stron")
                        break
                    
                    # Dodaj zadania
                    while not self.queue.empty() and len(futures) < self.config.max_workers:
                        url = self.queue.get()
                        if url in self.stats.visited:
                            continue
                        future = executor.submit(self._process, url)
                        futures[future] = url
                    
                    # Zbieraj wyniki
                    done = [f for f in futures if f.done()]
                    for future in done:
                        url = futures.pop(future)
                        try:
                            new_links = future.result()
                            for link in new_links:
                                self.queue.put(link)
                        except Exception as e:
                            print(f"❌ Błąd wątku: {e}")
                            self.stats.add_error(f"{url} | Błąd wątku: {type(e).__name__}: {e}")
                    
                    if self.queue.empty() and not futures:
                        print("\n⚠️  Brak więcej linków do przetworzenia")
                        break
                    
                    time.sleep(0.01)
        finally:
            self.storage.close()
        
        self._print_summary()
    
    def _process(self, url):
        """Przetwarza URL"""
        if not self.stats.mark_visited(url):
            return []
        
        visited, queued, _ = self.stats.get_counts()
        print(f"🔍 [{visited}/{queued}] {url}")
        
        # Pobierz
        success, content, error = self.http.fetch(url)
        
        if not success:
            self.stats.add_error(f"{url} | {error}")
            print(f"   ❌ Błąd pobierania")
            return []
        
        # Parsuj
        try:
            links, errors, text = self.parser.parse(url, content)
            self.stats.add_errors(errors)
        except Exception as e:
            self.stats.add_error(f"{url} | Błąd parsowania HTML: {type(e).__name__}: {e}")
            print(f"   ❌ Błąd parsowania")
            return []
        
        # Zapisz
        if not self.storage.save_page(url, text):
            self.stats.add_error(f"{url} | Błąd zapisu do pliku")
        
        # Dodaj nowe linki
        new = self.stats.add_queued(links)
        
        if new:
            _, total, _ = self.stats.get_counts()
            print(f"   ✅ Zapisano | +{len(new)} nowych linków (razem: {total})")
        else:
            print(f"   ✅ Zapisano")
        
        return new
    
    def _print_summary(self):
        visited, queued, errors = self.stats.get_counts()
        elapsed = self.stats.get_elapsed_time()
        
        print(f"\n{'='*60}")
        print(f"✅ CRAWLING ZAKOŃCZONY")
        print(f"{'='*60}")
        print(f"⏱️  Czas: {elapsed:.2f}s ({elapsed/60:.1f} min)")
        print(f"📊 Przetworzone strony: {visited}")
        print(f"🔗 Znalezione linki: {queued}")
        print(f"❌ Błędów: {errors}")
        if visited > 0:
            print(f"⚡ Prędkość: {visited/elapsed:.2f} stron/s")
        print(f"{'='*60}")
        
        # Zapisz błędy
        error_list = self.stats.get_errors()
        if error_list:
            self.storage.save_errors(error_list)
            print(f"\n❌ Błędy zapisano w: error_links.txt ({len(error_list)} błędów)")
        
        # Statystyki plików
        print(f"\n💾 Zapisane pliki:")
        texts_size = self.storage.get_file_size_mb("teksty.txt")
        if texts_size > 0:
            print(f"   📝 teksty.txt ({texts_size:.2f} MB)")
        links_size = self.storage.get_file_size_mb("all_links.txt")
        if links_size > 0:
            print(f"   🔗 all_links.txt ({links_size * 1024:.1f} KB)")
        if os.path.exists("error_links.txt"):
            err_size = self.storage.get_file_size_mb("error_links.txt")
            print(f"   ❌ error_links.txt ({err_size * 1024:.1f} KB)")
        
        print(f"\n🎉 CRAWLING GOTOWY!")
        print(f"   ✅ Pomyślnie: {visited}")
        print(f"   ❌ Błędy: {errors}")
        print(f"   🔗 Odkryte linki: {queued}")


# ============================================================================
# DEDUPLIKATOR
# ============================================================================
class Deduplicator:
    """Deduplikuje teksty"""
    SEP_IN = "_" * 80
    SEP_OUT = "_" * 50
    
    def __init__(self, input_file="teksty.txt", output_file="teksty_unikalne.txt"):
        self.input = input_file
        self.output = output_file
    
    def run(self):
        print(f"\n{'='*60}")
        print("🧹 DEDUPLIKATOR TEKSTU")
        print(f"{'='*60}")
        print(f"\n📄 Źródło: {self.input}")
        print(f"💾 Cel: {self.output}\n")
        
        start = time.time()
        
        try:
            print("📖 Wczytuję plik...")
            with open(self.input, 'r', encoding='utf-8') as f:
                content = f.read()
            
            sections = content.split(self.SEP_IN)
            if sections and not sections[-1].strip():
                sections.pop()
            
            print(f"📊 Znaleziono {len(sections)} sekcji\n")
            
            total_lines = 0
            unique_lines = 0
            processed = []
            
            for i, section in enumerate(sections, 1):
                lines = section.split('\n')
                seen = set()
                unique = []
                
                for line in lines:
                    total_lines += 1
                    if line not in seen:
                        seen.add(line)
                        unique.append(line)
                        unique_lines += 1
                
                processed.append('\n'.join(unique))
                
                if i % 10 == 0:
                    print(f"   Przetworzono {i}/{len(sections)} sekcji...")
            
            print(f"\n💾 Zapisuję wynik...")
            with open(self.output, 'w', encoding='utf-8') as f:
                for i, section in enumerate(processed):
                    f.write(section)
                    if i < len(processed) - 1:
                        if not section.endswith('\n'):
                            f.write('\n')
                        f.write(self.SEP_OUT + '\n')
            
            elapsed = time.time() - start
            removed = total_lines - unique_lines
            
            print(f"\n{'='*60}")
            print(f"✅ DEDUPLIKACJA ZAKOŃCZONA")
            print(f"{'='*60}")
            print(f"⏱️  Czas: {elapsed:.2f}s")
            print(f"📊 Sekcji: {len(sections)}")
            print(f"📝 Łącznie linii: {total_lines}")
            print(f"✅ Unikalne: {unique_lines}")
            print(f"🗑️  Usunięte: {removed}")
            if total_lines > 0:
                print(f"💾 Oszczędność: {(removed/total_lines*100):.1f}%")
            print(f"{'='*60}")
            
            try:
                size = os.path.getsize(self.output) / (1024 * 1024)
                print(f"\n💾 Plik wyjściowy:")
                print(f"   📝 {self.output} ({size:.2f} MB)")
            except:
                pass
            
            return True
        except FileNotFoundError:
            print(f"❌ Błąd: Plik '{self.input}' nie istnieje!")
            return False
        except Exception as e:
            print(f"❌ Błąd deduplikacji: {e}")
            return False


# ============================================================================
# GUI
# ============================================================================
class ConsoleRedirect:
    """Przekierowuje print() do GUI"""
    def __init__(self, widget):
        self.widget = widget
    
    def write(self, text):
        try:
            self.widget.insert(tk.END, text)
            self.widget.see(tk.END)
            self.widget.update_idletasks()
        except:
            pass
    
    def flush(self):
        pass


class GUI:
    """Interfejs graficzny"""
    def __init__(self, root):
        self.root = root
        self.root.title("🕷️ Web Crawler + Ekstraktor")
        self.root.geometry("900x850")
        self.root.configure(bg="#f0f0f0")
        
        self.crawler = None
        self.stop_event = Event()
        self.running = False
        self.stats_job = None
        
        self._build()
    
    def _build(self):
        """Buduje UI"""
        # URL
        f1 = tk.Frame(self.root, bg="#f0f0f0", padx=10, pady=10)
        f1.pack(fill=tk.X)
        tk.Label(f1, text="📍 URL Strony:", font=("Arial", 12, "bold"), bg="#f0f0f0").pack(anchor=tk.W)
        self.url_entry = tk.Entry(f1, font=("Arial", 11), width=80)
        self.url_entry.pack(fill=tk.X, pady=5)
        self.url_entry.insert(0, "https://example.com")
        
        # Parametry
        f2 = tk.LabelFrame(self.root, text="⚙️ Parametry", font=("Arial", 11, "bold"),
                          bg="#f0f0f0", padx=10, pady=10)
        f2.pack(fill=tk.X, padx=10, pady=5)
        
        # Max stron
        r1 = tk.Frame(f2, bg="#f0f0f0")
        r1.pack(fill=tk.X, pady=3)
        tk.Label(r1, text="📊 Max stron:", width=15, anchor=tk.W, bg="#f0f0f0").pack(side=tk.LEFT)
        self.max_pages = tk.Spinbox(r1, from_=1, to=100000, width=15, font=("Arial", 10))
        self.max_pages.delete(0, tk.END)
        self.max_pages.insert(0, "1000")
        self.max_pages.pack(side=tk.LEFT, padx=5)
        tk.Label(r1, text="(min: 1)", font=("Arial", 9), fg="#666", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        
        # Wątki
        r2 = tk.Frame(f2, bg="#f0f0f0")
        r2.pack(fill=tk.X, pady=3)
        tk.Label(r2, text="🔧 Liczba wątków:", width=15, anchor=tk.W, bg="#f0f0f0").pack(side=tk.LEFT)
        self.workers = tk.Spinbox(r2, from_=1, to=50, width=15, font=("Arial", 10))
        self.workers.delete(0, tk.END)
        self.workers.insert(0, "10")
        self.workers.pack(side=tk.LEFT, padx=5)
        tk.Label(r2, text="(min: 1, max: 50)", font=("Arial", 9), fg="#666", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        
        # Opóźnienie
        r3 = tk.Frame(f2, bg="#f0f0f0")
        r3.pack(fill=tk.X, pady=3)
        tk.Label(r3, text="⏱️ Opóźnienie (s):", width=15, anchor=tk.W, bg="#f0f0f0").pack(side=tk.LEFT)
        self.delay = tk.Spinbox(r3, from_=0.3, to=10.0, increment=0.1, width=15, 
                               font=("Arial", 10), format="%.1f")
        self.delay.delete(0, tk.END)
        self.delay.insert(0, "0.3")
        self.delay.pack(side=tk.LEFT, padx=5)
        tk.Label(r3, text="(min: 0.3)", font=("Arial", 9), fg="#666", bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        
        # Przyciski START/STOP
        f3 = tk.Frame(self.root, bg="#f0f0f0", pady=10)
        f3.pack(fill=tk.X)
        
        self.start_btn = tk.Button(f3, text="🚀 SCRAPUJ", font=("Arial", 14, "bold"),
                                   bg="#4CAF50", fg="white", command=self.start,
                                   cursor="hand2", padx=30, pady=10)
        self.start_btn.pack(side=tk.LEFT, padx=(250, 10))
        
        self.stop_btn = tk.Button(f3, text="⛔ PRZERWIJ", font=("Arial", 14, "bold"),
                                  bg="#F44336", fg="white", command=self.stop,
                                  cursor="hand2", padx=30, pady=10, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)
        
        # Statystyki
        f4 = tk.LabelFrame(self.root, text="📊 Statystyki Live", font=("Arial", 11, "bold"),
                          bg="#f0f0f0", padx=10, pady=10)
        f4.pack(fill=tk.X, padx=10, pady=5)
        
        grid = tk.Frame(f4, bg="#f0f0f0")
        grid.pack(fill=tk.X)
        
        tk.Label(grid, text="✅ Przetworzone:", width=18, anchor=tk.W, bg="#f0f0f0", 
                font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.stat_visited = tk.Label(grid, text="0", width=12, anchor=tk.W,
                                     font=("Arial", 10, "bold"), fg="#2196F3", bg="#f0f0f0")
        self.stat_visited.grid(row=0, column=1, sticky=tk.W)
        
        tk.Label(grid, text="🔗 Znalezione linki:", width=18, anchor=tk.W, bg="#f0f0f0",
                font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.stat_links = tk.Label(grid, text="0", width=12, anchor=tk.W,
                                   font=("Arial", 10, "bold"), fg="#FF9800", bg="#f0f0f0")
        self.stat_links.grid(row=1, column=1, sticky=tk.W)
        
        tk.Label(grid, text="❌ Błędy:", width=18, anchor=tk.W, bg="#f0f0f0",
                font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.stat_errors = tk.Label(grid, text="0", width=12, anchor=tk.W,
                                    font=("Arial", 10, "bold"), fg="#F44336", bg="#f0f0f0")
        self.stat_errors.grid(row=2, column=1, sticky=tk.W)
        
        tk.Label(grid, text="⏱️ Czas:", width=18, anchor=tk.W, bg="#f0f0f0",
                font=("Arial", 10)).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.stat_time = tk.Label(grid, text="0.0s", width=12, anchor=tk.W,
                                  font=("Arial", 10, "bold"), fg="#9C27B0", bg="#f0f0f0")
        self.stat_time.grid(row=3, column=1, sticky=tk.W)
        
        self.progress = ttk.Progressbar(f4, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=5)
        
        # Konsola
        f5 = tk.LabelFrame(self.root, text="📋 Logi", font=("Arial", 11, "bold"),
                          bg="#f0f0f0", padx=10, pady=10)
        f5.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.console = scrolledtext.ScrolledText(f5, height=15, font=("Consolas", 9),
                                                 bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.console.pack(fill=tk.BOTH, expand=True)
        
        # Download
        f6 = tk.Frame(self.root, bg="#f0f0f0", pady=10)
        f6.pack(fill=tk.X, padx=10)
        
        self.dl_texts = tk.Button(f6, text="📥 Pobierz Teksty", font=("Arial", 11, "bold"),
                                 bg="#2196F3", fg="white", command=self.download_texts,
                                 cursor="hand2", padx=20, pady=8, state=tk.DISABLED)
        self.dl_texts.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        self.dl_errors = tk.Button(f6, text="⚠️ Pobierz Errory", font=("Arial", 11, "bold"),
                                  bg="#FF5722", fg="white", command=self.download_errors,
                                  cursor="hand2", padx=20, pady=8, state=tk.DISABLED)
        self.dl_errors.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
    
    def start(self):
        if self.running:
            messagebox.showwarning("Ostrzeżenie", "Crawling już trwa!")
            return
        
        # Walidacja
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Błąd", "Podaj URL!")
            return
        
        try:
            max_pages = int(self.max_pages.get())
            workers = int(self.workers.get())
            delay = float(self.delay.get())
            
            if max_pages < 1:
                messagebox.showerror("Błąd", "Minimalna liczba stron to 1!")
                return
            if workers < 1:
                messagebox.showerror("Błąd", "Minimalna liczba wątków to 1!")
                return
            if workers > 50:
                messagebox.showerror("Błąd", "Maksymalna liczba wątków to 50!")
                return
            if delay < 0.3:
                messagebox.showerror("Błąd", "Minimalne opóźnienie to 0.3s!")
                return
        except ValueError:
            messagebox.showerror("Błąd", "Nieprawidłowe parametry!")
            return
        
        # UI
        self.stop_event.clear()
        self.start_btn.config(state=tk.DISABLED, bg="#cccccc")
        self.stop_btn.config(state=tk.NORMAL, bg="#F44336")
        self.dl_texts.config(state=tk.DISABLED)
        self.dl_errors.config(state=tk.DISABLED)
        self.console.delete(1.0, tk.END)
        self.stat_visited.config(text="0")
        self.stat_links.config(text="0")
        self.stat_errors.config(text="0")
        self.stat_time.config(text="0.0s")
        self.progress.start()
        
        # Redirect
        sys.stdout = ConsoleRedirect(self.console)
        
        # Thread
        self.running = True
        config = Config(url, max_pages, workers, delay)
        config.normalize_url()
        
        threading.Thread(target=self._run, args=(config,), daemon=True).start()
        self._schedule_stats_update()
    
    def stop(self):
        if self.running:
            self.stop_event.set()
            self.stop_btn.config(state=tk.DISABLED, bg="#cccccc")
            print("\n⚠️  Żądanie przerwania... Proszę czekać...")
    
    def _run(self, config):
        try:
            self.crawler = Crawler(config, self.stop_event)
            self.crawler.run()
            
            if not self.stop_event.is_set():
                Deduplicator().run()
            
            self.root.after(0, lambda: self.dl_texts.config(state=tk.NORMAL))
            if os.path.exists("error_links.txt"):
                self.root.after(0, lambda: self.dl_errors.config(state=tk.NORMAL))
        except Exception as e:
            error_msg = f"Błąd podczas crawlingu:\n{e}"
            self.root.after(0, lambda: messagebox.showerror("Błąd", error_msg))
            print(f"\n❌ {error_msg}")
        finally:
            self.running = False
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL, bg="#4CAF50"))
            self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED, bg="#cccccc"))
            self.root.after(0, self.progress.stop)
            self.root.after(100, self._final_stats_update)
    
    def _schedule_stats_update(self):
        if self.running:
            self._update_stats()
            self.stats_job = self.root.after(300, self._schedule_stats_update)
    
    def _update_stats(self):
        if self.crawler:
            try:
                v, l, e = self.crawler.stats.get_counts()
                t = self.crawler.stats.get_elapsed_time()
                self.stat_visited.config(text=str(v))
                self.stat_links.config(text=str(l))
                self.stat_errors.config(text=str(e))
                self.stat_time.config(text=f"{t:.1f}s")
            except:
                pass
    
    def _final_stats_update(self):
        if self.crawler:
            try:
                v, l, e = self.crawler.stats.get_counts()
                t = self.crawler.stats.get_elapsed_time()
                self.stat_visited.config(text=str(v))
                self.stat_links.config(text=str(l))
                self.stat_errors.config(text=str(e))
                self.stat_time.config(text=f"{t:.1f}s")
            except:
                pass
    
    def download_texts(self):
        self._download("teksty_unikalne.txt", "Zapisz teksty")
    
    def download_errors(self):
        self._download("error_links.txt", "Zapisz errory")
    
    def _download(self, source, title):
        if not os.path.exists(source):
            messagebox.showerror("Błąd", f"Plik {source} nie istnieje!")
            return
        
        dest = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            initialfile=source
        )
        
        if dest:
            try:
                shutil.copy(source, dest)
                messagebox.showinfo("Sukces", f"Zapisano:\n{dest}")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zapisać pliku:\n{e}")


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    GUI(root)
    root.mainloop()
