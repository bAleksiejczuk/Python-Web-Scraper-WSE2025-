import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import queue
import os


# ============================================================================
# KLASA: KONFIGURACJA
# ============================================================================
class Config:
    """Przechowuje konfigurację crawlera"""
    
    def __init__(self):
        self.url = None
        self.max_pages = 1000
        self.max_workers = 10
        self.delay = 0.3
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def load_from_user(self):
        """Wczytuje konfigurację od użytkownika"""
        print("="*60)
        print("🕷️  WEB CRAWLER + EKSTRAKTOR TEKSTU")
        print("="*60)
        
        self.url = input("\n📍 URL strony: ").strip()
        if not self.url.startswith(('http://', 'https://')):
            self.url = 'https://' + self.url
        
        max_pages = input("📊 Max stron (Enter = 1000): ").strip()
        self.max_pages = int(max_pages) if max_pages else 1000
        
        max_workers = input("🔧 Wątków (Enter = 10): ").strip()
        self.max_workers = int(max_workers) if max_workers else 10
        
        delay = input("⏱️  Opóźnienie między requestami w sekundach (Enter = 0.3): ").strip()
        self.delay = float(delay) if delay else 0.3
    
    def print_info(self, allowed_domains):
        """Wyświetla informacje o konfiguracji"""
        print(f"\n🚀 Start: {self.url}")
        print(f"📍 Domeny: {', '.join(allowed_domains)}")
        print(f"🔧 Wątków: {self.max_workers}")
        print(f"📊 Limit: {self.max_pages}")
        print(f"⏱️  Opóźnienie: {self.delay}s\n")


# ============================================================================
# KLASA: ZARZĄDZANIE DOMENAMI
# ============================================================================
class DomainManager:
    """Zarządza domenami dozwolonymi do crawlingu"""
    
    def __init__(self, start_url):
        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        self.allowed_domains = self._create_allowed_domains()
    
    def _create_allowed_domains(self):
        """Tworzy listę dozwolonych domen (z www i bez)"""
        if self.base_domain.startswith('www.'):
            alt_domain = self.base_domain[4:]
            return [self.base_domain, alt_domain]
        else:
            alt_domain = 'www.' + self.base_domain
            return [self.base_domain, alt_domain]
    
    def is_allowed(self, domain):
        """Sprawdza czy domena jest dozwolona"""
        return domain in self.allowed_domains


# ============================================================================
# KLASA: EKSTRAKTOR HTML
# ============================================================================
class HTMLExtractor:
    """Wyciąga linki i tekst z HTML"""
    
    def __init__(self, domain_manager):
        self.domain_manager = domain_manager
    
    def extract(self, url, html_content):
        """
        Wyciąga linki i tekst z HTML
        Zwraca: (lista_linków, lista_błędów_z_tej_strony)
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        links, errors = self._extract_links(url, soup)
        
        return links, errors
    
    def _extract_links(self, source_url, soup):
        """Wyciąga linki z HTML"""
        links = []
        errors = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Pomiń specjalne linki
            if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            
            try:
                full_url = urljoin(source_url, href)
                parsed = urlparse(full_url)
                
                # Sprawdź czy link wewnętrzny
                is_internal = self.domain_manager.is_allowed(parsed.netloc) or parsed.netloc == ''
                
                # Walidacja
                if not parsed.scheme or not parsed.netloc:
                    if is_internal or href.startswith(('/', './', '../', 'wp-content', 'uploads')):
                        errors.append(f"{href} | Niepoprawny URL (brak schematu/domeny) | Źródło: {source_url}")
                    continue
                
                # Pomiń linki zewnętrzne
                if not self.domain_manager.is_allowed(parsed.netloc):
                    continue
                
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                
                # Pomiń pliki binarne
                if clean_url.lower().endswith(('.pdf', '.jpg', '.png', '.zip', '.doc', 
                                               '.docx', '.xls', '.xlsx', '.gif', '.jpeg', 
                                               '.svg', '.mp4', '.avi', '.mp3')):
                    continue
                
                links.append(clean_url)
                
            except Exception as e:
                errors.append(f"{href} | Błąd parsowania linku: {type(e).__name__}: {e} | Źródło: {source_url}")
        
        return links, errors
    
    def _extract_text(self, soup):
        """Wyciąga tekst z HTML"""
        # Usuń niepotrzebne elementy
        for element in soup(['script', 'style', 'head', 'title', 'meta', 'iframe', 'noscript']):
            element.extract()
        
        # Formatowanie
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
        
        # Czyszczenie
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')
        
        return text.strip()


# ============================================================================
# KLASA: ZARZĄDZANIE PLIKAMI
# ============================================================================
class FileManager:
    """Zarządza zapisem do plików"""
    
    def __init__(self):
        self.separator = "_" * 80
        self.file_lock = Lock()
        
        self.texts_file = open("teksty.txt", 'w', encoding='utf-8')
        self.links_file = open("all_links.txt", 'w', encoding='utf-8')
    
    def save_page(self, url, text):
        """Zapisuje stronę do pliku"""
        with self.file_lock:
            try:
                self.texts_file.write(f"{url}\n\n")
                self.texts_file.write(f"{text}\n\n")
                self.texts_file.write(f"{self.separator}\n\n")
                self.texts_file.flush()
                
                self.links_file.write(f"{url}\n")
                self.links_file.flush()
                
                return True
            except Exception as e:
                print(f"   ⚠️  Błąd zapisu: {e}")
                return False
    
    def save_errors(self, errors):
        """Zapisuje błędy do pliku"""
        if errors:
            with open("error_links.txt", 'w', encoding='utf-8') as f:
                for error in sorted(errors):
                    f.write(error + '\n')
    
    def close(self):
        """Zamyka pliki"""
        self.texts_file.close()
        self.links_file.close()
    
    def get_file_stats(self):
        """Zwraca statystyki plików"""
        stats = {}
        try:
            stats['texts_size'] = os.path.getsize("teksty.txt") / (1024 * 1024)  # MB
            stats['links_size'] = os.path.getsize("all_links.txt") / 1024  # KB
            if os.path.exists("error_links.txt"):
                stats['errors_size'] = os.path.getsize("error_links.txt") / 1024  # KB
        except:
            pass
        return stats


# ============================================================================
# KLASA: STATYSTYKI CRAWLERA
# ============================================================================
class CrawlerStats:
    """Zbiera statystyki crawlingu"""
    
    def __init__(self):
        self.visited = set()
        self.all_links = set()
        self.error_links = []
        
        self.visited_lock = Lock()
        self.links_lock = Lock()
        self.error_lock = Lock()
        
        self.start_time = time.time()
    
    def mark_visited(self, url):
        """Oznacza URL jako odwiedzony"""
        with self.visited_lock:
            if url in self.visited:
                return False
            self.visited.add(url)
            return True
    
    def add_links(self, links):
        """Dodaje nowe linki"""
        added = []
        with self.links_lock:
            for link in links:
                if link not in self.visited and link not in self.all_links:
                    self.all_links.add(link)
                    added.append(link)
        return added
    
    def add_error(self, error):
        """Dodaje błąd"""
        with self.error_lock:
            self.error_links.append(error)
    
    def get_counts(self):
        """Zwraca liczniki"""
        with self.visited_lock:
            visited_count = len(self.visited)
        with self.links_lock:
            links_count = len(self.all_links)
        with self.error_lock:
            errors_count = len(self.error_links)
        
        return visited_count, links_count, errors_count
    
    def get_elapsed_time(self):
        """Zwraca czas od rozpoczęcia"""
        return time.time() - self.start_time
    
    def print_summary(self):
        """Wyświetla podsumowanie"""
        elapsed = self.get_elapsed_time()
        visited_count, links_count, errors_count = self.get_counts()
        
        print(f"\n" + "="*60)
        print(f"✅ CRAWLING ZAKOŃCZONY")
        print(f"="*60)
        print(f"⏱️  Czas: {elapsed:.2f}s ({elapsed/60:.1f} min)")
        print(f"📊 Przetworzone strony: {visited_count}")
        print(f"🔗 Znalezione linki: {links_count}")
        print(f"❌ Błędów: {errors_count}")
        if visited_count > 0:
            print(f"⚡ Prędkość: {visited_count/elapsed:.2f} stron/s")
        print(f"="*60)


# ============================================================================
# KLASA: POBIERANIE STRON
# ============================================================================
class PageFetcher:
    """Pobiera strony HTTP"""
    
    def __init__(self, config):
        self.config = config
    
    def fetch(self, url):
        """
        Pobiera stronę
        Zwraca: (status, html_lub_błąd)
        status: 'ok', 'error', 'not_html'
        """
        time.sleep(self.config.delay)
        
        try:
            response = requests.get(url, timeout=15, headers=self.config.headers)
            response.raise_for_status()
            
            # Sprawdź typ zawartości
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return 'not_html', f"Content-Type: {content_type}"
            
            return 'ok', response.text
            
        except requests.exceptions.RequestException as e:
            return 'error', f"{type(e).__name__}: {e}"


# ============================================================================
# KLASA: GŁÓWNY CRAWLER
# ============================================================================
class WebCrawler:
    """Główna klasa crawlera"""
    
    def __init__(self, config):
        self.config = config
        self.domain_manager = DomainManager(config.url)
        self.extractor = HTMLExtractor(self.domain_manager)
        self.fetcher = PageFetcher(config)
        self.file_manager = FileManager()
        self.stats = CrawlerStats()
        
        self.to_visit = queue.Queue()
        self.to_visit.put(config.url)
        self.stats.all_links.add(config.url)
    
    def process_url(self, url):
        """Przetwarza jeden URL"""
        # Sprawdź czy już odwiedzony
        if not self.stats.mark_visited(url):
            return []
        
        visited_count, links_count, _ = self.stats.get_counts()
        print(f"🔍 [{visited_count}/{links_count}] {url}")
        
        # Pobierz stronę
        status, content = self.fetcher.fetch(url)
        
        if status == 'error':
            self.stats.add_error(f"{url} | {content}")
            print(f"   ❌ Błąd pobierania")
            return []
        
        if status == 'not_html':
            self.stats.add_error(f"{url} | Nie-HTML ({content})")
            print(f"   ⚠️  Nie-HTML")
            return []
        
        # Wyciągnij linki i tekst
        try:
            new_links, link_errors = self.extractor.extract(url, content)
            soup = BeautifulSoup(content, 'html.parser')
            text = self.extractor._extract_text(soup)
            
            # Zapisz błędy z parsowania linków
            for error in link_errors:
                self.stats.add_error(error)
                
        except Exception as e:
            self.stats.add_error(f"{url} | Błąd parsowania HTML: {type(e).__name__}: {e}")
            print(f"   ❌ Błąd parsowania")
            return []
        
        # Zapisz
        if not self.file_manager.save_page(url, text):
            self.stats.add_error(f"{url} | Błąd zapisu do pliku")
        
        # Dodaj nowe linki
        added = self.stats.add_links(new_links)
        
        if added:
            _, total_links, _ = self.stats.get_counts()
            print(f"   ✅ Zapisano | +{len(added)} nowych linków (razem: {total_links})")
        else:
            print(f"   ✅ Zapisano")
        
        return added
    
    def run(self):
        """Uruchamia crawling"""
        self.config.print_info(self.domain_manager.allowed_domains)
        
        try:
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = {}
                
                while True:
                    visited_count, _, _ = self.stats.get_counts()
                    
                    # Sprawdź limit
                    if visited_count >= self.config.max_pages:
                        print(f"\n⚠️  Osiągnięto limit {self.config.max_pages} stron")
                        break
                    
                    # Dodaj nowe zadania
                    while not self.to_visit.empty() and len(futures) < self.config.max_workers:
                        current_url = self.to_visit.get()
                        
                        if current_url in self.stats.visited:
                            continue
                        
                        future = executor.submit(self.process_url, current_url)
                        futures[future] = current_url
                    
                    # Zbieraj wyniki
                    if futures:
                        done_futures = [f for f in futures.keys() if f.done()]
                        for future in done_futures:
                            current_url = futures.pop(future)
                            try:
                                new_links = future.result()
                                for link in new_links:
                                    self.to_visit.put(link)
                            except Exception as e:
                                print(f"❌ Błąd wątku: {e}")
                                self.stats.add_error(f"{current_url} | Błąd wątku: {type(e).__name__}: {e}")
                    
                    # Warunek zakończenia
                    if self.to_visit.empty() and not futures:
                        print("\n⚠️  Brak więcej linków do przetworzenia")
                        break
                    
                    time.sleep(0.01)
        
        finally:
            self.file_manager.close()
        
        # Podsumowanie
        self.stats.print_summary()
        
        # Zapisz błędy
        if self.stats.error_links:
            self.file_manager.save_errors(self.stats.error_links)
            print(f"\n❌ Błędy zapisano w: error_links.txt ({len(self.stats.error_links)} błędów)")
        
        # Statystyki plików
        file_stats = self.file_manager.get_file_stats()
        if file_stats:
            print(f"\n💾 Zapisane pliki:")
            if 'texts_size' in file_stats:
                print(f"   📝 teksty.txt ({file_stats['texts_size']:.2f} MB)")
            if 'links_size' in file_stats:
                print(f"   🔗 all_links.txt ({file_stats['links_size']:.1f} KB)")
            if 'errors_size' in file_stats:
                print(f"   ❌ error_links.txt ({file_stats['errors_size']:.1f} KB)")
        
        visited_count, links_count, errors_count = self.stats.get_counts()
        print(f"\n🎉 CRAWLING GOTOWY!")
        print(f"   ✅ Pomyślnie: {visited_count}")
        print(f"   ❌ Błędy: {errors_count}")
        print(f"   🔗 Odkryte linki: {links_count}")


# ============================================================================
# KLASA: DEDUPLIKATOR
# ============================================================================
class TextDeduplicator:
    """Usuwa duplikaty z pliku tekstowego"""
    
    def __init__(self, input_file="teksty.txt", output_file="teksty_unikalne.txt"):
        self.input_file = input_file
        self.output_file = output_file
        self.separator = "_" * 80
        self.section_separator = "_" * 50
    
    def deduplicate(self):
        """Usuwa duplikaty"""
        print("\n" + "="*60)
        print("🧹 DEDUPLIKATOR TEKSTU")
        print("="*60)
        print(f"\n📄 Źródło: {self.input_file}")
        print(f"💾 Cel: {self.output_file}\n")
        
        start_time = time.time()
        
        try:
            # Wczytaj plik
            print("📖 Wczytuję plik...")
            with open(self.input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Podziel na sekcje
            sections = content.split(self.separator)
            
            if sections and not sections[-1].strip():
                sections.pop()
            
            print(f"📊 Znaleziono {len(sections)} sekcji\n")
            
            # Statystyki
            total_lines = 0
            total_unique = 0
            
            # Przetwórz każdą sekcję
            processed = []
            for i, section in enumerate(sections, 1):
                lines = section.split('\n')
                
                # Usuń duplikaty zachowując kolejność
                unique = []
                seen = set()
                
                for line in lines:
                    total_lines += 1
                    if line not in seen:
                        seen.add(line)
                        unique.append(line)
                        total_unique += 1
                
                processed.append('\n'.join(unique))
                
                if i % 10 == 0:
                    print(f"   Przetworzono {i}/{len(sections)} sekcji...")
            
            # Zapisz wynik
            print(f"\n💾 Zapisuję wynik...")
            with open(self.output_file, 'w', encoding='utf-8') as f:
                for i, section in enumerate(processed):
                    f.write(section)
                    
                    # Dodaj separator (oprócz ostatniej sekcji)
                    if i < len(processed) - 1:
                        if not section.endswith('\n'):
                            f.write('\n')
                        f.write(self.section_separator + '\n')
            
            # Podsumowanie deduplikacji
            elapsed = time.time() - start_time
            removed = total_lines - total_unique
            
            print(f"\n" + "="*60)
            print(f"✅ DEDUPLIKACJA ZAKOŃCZONA")
            print(f"="*60)
            print(f"⏱️  Czas: {elapsed:.2f}s")
            print(f"📊 Sekcji: {len(sections)}")
            print(f"📝 Łącznie linii: {total_lines}")
            print(f"✅ Unikalne: {total_unique}")
            print(f"🗑️  Usunięte: {removed}")
            if total_lines > 0:
                print(f"💾 Oszczędność: {(removed/total_lines*100):.1f}%")
            print(f"="*60)
            
            # Statystyka rozmiaru pliku
            try:
                size = os.path.getsize(self.output_file) / (1024 * 1024)  # MB
                print(f"\n💾 Plik wyjściowy:")
                print(f"   📝 {self.output_file} ({size:.2f} MB)")
            except:
                pass
            
            return True
            
        except FileNotFoundError:
            print(f"❌ Błąd: Plik '{self.input_file}' nie istnieje!")
            return False
        except Exception as e:
            print(f"❌ Błąd deduplikacji: {e}")
            return False


# ============================================================================
# FUNKCJA GŁÓWNA
# ============================================================================
def main():
    """Główna funkcja programu"""
    total_start = time.time()
    
    # 1. Konfiguracja
    config = Config()
    config.load_from_user()
    
    # 2. Crawling
    crawler = WebCrawler(config)
    crawler.run()
    
    # 3. Deduplikacja
    deduplicator = TextDeduplicator()
    deduplicator.deduplicate()
    
    # 4. Końcowe podsumowanie
    total_elapsed = time.time() - total_start
    
    print(f"\n" + "="*60)
    print(f"🎉 WSZYSTKO GOTOWE!")
    print(f"="*60)
    print(f"⏱️  Całkowity czas: {total_elapsed:.2f}s ({total_elapsed/60:.1f} min)")
    print(f"\n📦 PLIKI WYJŚCIOWE:")
    print(f"   📝 teksty.txt - oryginalne teksty")
    print(f"   🧹 teksty_unikalne.txt - teksty bez duplikatów")
    print(f"   🔗 all_links.txt - wszystkie znalezione linki")
    
    visited_count, _, errors_count = crawler.stats.get_counts()
    if errors_count > 0:
        print(f"   ❌ error_links.txt - błędy podczas crawlingu")
    
    print(f"\n✨ Dziękuję za skorzystanie z crawlera!")
    print(f"="*60)


# ============================================================================
# URUCHOMIENIE
# ============================================================================
if __name__ == "__main__":
    main()
