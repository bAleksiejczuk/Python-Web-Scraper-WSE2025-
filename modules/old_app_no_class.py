import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import queue
import os

# ============================================================================
# KONFIGURACJA
# ============================================================================
print("="*60)
print("🕷️  WEB CRAWLER + EKSTRAKTOR TEKSTU")
print("="*60)

url = input("\n📍 URL strony: ").strip()
if not url.startswith(('http://', 'https://')):
    url = 'https://' + url

max_pages = input("📊 Max stron (Enter = 1000): ").strip()
max_pages = int(max_pages) if max_pages else 1000

max_workers = input("🔧 Wątków (Enter = 10): ").strip()
max_workers = int(max_workers) if max_workers else 10

delay = input("⏱️  Opóźnienie między requestami w sekundach (Enter = 0.3): ").strip()
delay = float(delay) if delay else 0.3

# ============================================================================
# INICJALIZACJA
# ============================================================================
parsed_start = urlparse(url)
base_domain = parsed_start.netloc

# Obsługa www i bez www
if base_domain.startswith('www.'):
    base_domain_alt = base_domain[4:]
    allowed_domains = [base_domain, base_domain_alt]
else:
    base_domain_alt = 'www.' + base_domain
    allowed_domains = [base_domain, base_domain_alt]

visited = set()
error_links = []
all_links = set([url])
to_visit = queue.Queue()
to_visit.put(url)

visited_lock = Lock()
error_lock = Lock()
links_lock = Lock()
file_lock = Lock()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

print(f"\n🚀 Start: {url}")
print(f"📍 Domeny: {', '.join(allowed_domains)}")
print(f"🔧 Wątków: {max_workers}")
print(f"📊 Limit: {max_pages}")
print(f"⏱️  Opóźnienie: {delay}s\n")

start_time = time.time()

# Otwórz pliki wyjściowe
output_texts = open("teksty.txt", 'w', encoding='utf-8')
output_links = open("all_links.txt", 'w', encoding='utf-8')

separator = "_" * 80

# ============================================================================
# FUNKCJA GŁÓWNA - POBIERZ LINKI + TEKST
# ============================================================================
def extract_links_and_text(url, html_content):
    """
    Wyciąga zarówno linki jak i tekst z HTML
    Zwraca: (lista_linków, wyekstrahowany_tekst)
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # ========== EKSTRAKCJA LINKÓW ==========
    links = []
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        
        # Pomiń specjalne linki (ale nie loguj - to normalne)
        if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        
        try:
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            
            # ✅ SPRAWDŹ CZY TO LINK WEWNĘTRZNY
            is_internal = parsed.netloc in allowed_domains or parsed.netloc == ''
            
            # ❌ WALIDACJA: brak schematu lub domeny
            if not parsed.scheme or not parsed.netloc:
                # ✅ LOGUJ TYLKO JEŚLI TO PRÓBA LINKU WEWNĘTRZNEGO
                if is_internal or href.startswith(('/', './', '../', 'wp-content', 'uploads')):
                    with error_lock:
                        error_links.append(f"{href} | Niepoprawny URL (brak schematu/domeny) | Źródło: {url}")
                continue
            
            # ❌ LINK ZEWNĘTRZNY - pomijamy bez logowania
            if parsed.netloc not in allowed_domains:
                continue
            
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Pomiń pliki binarne (ale nie loguj - to normalne)
            if clean_url.lower().endswith(('.pdf', '.jpg', '.png', '.zip', '.doc', '.docx', '.xls', '.xlsx', '.gif', '.jpeg', '.svg', '.mp4', '.avi', '.mp3')):
                continue
            
            links.append(clean_url)
            
        except Exception as e:
            # ✅ LOGUJ WSZYSTKIE BŁĘDY PARSOWANIA
            with error_lock:
                error_links.append(f"{href} | Błąd parsowania linku: {type(e).__name__}: {e} | Źródło: {url}")
            continue
    
    # ========== EKSTRAKCJA TEKSTU ==========
    # ✅ JEDYNA ZMIANA: Usuń tylko script, style itp. BEZ nav, footer, header
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
    
    # Czyszczenie tekstu
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(line for line in lines if line)
    
    # Usuń wielokrotne puste linie
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    
    return links, text.strip()

# ============================================================================
# FUNKCJA PRZETWARZANIA URL
# ============================================================================
def process_url(url):
    """
    Przetwarza jeden URL:
    1. Pobiera HTML
    2. Wyciąga linki
    3. Wyciąga tekst
    4. Zapisuje wszystko
    """
    
    # Sprawdź czy już odwiedzony
    with visited_lock:
        if url in visited:
            return []
        visited.add(url)
        visited_count = len(visited)
    
    with links_lock:
        all_links_count = len(all_links)
    
    print(f"🔍 [{visited_count}/{all_links_count}] {url}")
    
    # Rate limiting
    time.sleep(delay)
    
    # ========== POBIERZ STRONĘ ==========
    try:
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        
    except requests.exceptions.RequestException as e:
        # ✅ OBSŁUGUJE WSZYSTKIE BŁĘDY: Timeout, ConnectionError, HTTPError, etc.
        with error_lock:
            error_links.append(f"{url} | {type(e).__name__}: {e}")
        print(f"   ❌ {type(e).__name__}")
        return []
    
    # ========== SPRAWDŹ TYP ZAWARTOŚCI ==========
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' not in content_type:
        with error_lock:
            error_links.append(f"{url} | Nie-HTML (Content-Type: {content_type})")
        print(f"   ⚠️  Nie-HTML: {content_type}")
        return []
    
    # ========== EKSTRAKCJA ==========
    try:
        new_links, text = extract_links_and_text(url, response.text)
    except Exception as e:
        with error_lock:
            error_links.append(f"{url} | Błąd parsowania HTML: {type(e).__name__}: {e}")
        print(f"   ❌ Błąd parsowania: {type(e).__name__}")
        return []
    
    # ========== ZAPISZ TEKST ==========
    with file_lock:
        try:
            output_texts.write(f"{url}\n\n")
            output_texts.write(f"{text}\n\n")
            output_texts.write(f"{separator}\n\n")
            output_texts.flush()
            
            output_links.write(f"{url}\n")
            output_links.flush()
            
        except Exception as e:
            print(f"   ⚠️  Błąd zapisu: {e}")
    
    # ========== DODAJ NOWE LINKI ==========
    added = []
    with links_lock:
        for link in new_links:
            if link not in visited and link not in all_links:
                all_links.add(link)
                added.append(link)
        updated_count = len(all_links)
    
    if added:
        print(f"   ✅ Zapisano | +{len(added)} nowych linków (razem: {updated_count})")
    else:
        print(f"   ✅ Zapisano")
    
    return added

# ============================================================================
# GŁÓWNA PĘTLA CRAWLINGU
# ============================================================================
try:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        
        while len(visited) < max_pages:
            # Dodaj nowe zadania
            while not to_visit.empty() and len(futures) < max_workers:
                current_url = to_visit.get()
                
                with visited_lock:
                    if current_url in visited:
                        continue
                
                future = executor.submit(process_url, current_url)
                futures[future] = current_url
            
            # Zbieraj wyniki
            if futures:
                done_futures = [f for f in futures.keys() if f.done()]
                for future in done_futures:
                    current_url = futures.pop(future)
                    try:
                        new_links = future.result()
                        for link in new_links:
                            to_visit.put(link)
                    except Exception as e:
                        print(f"❌ Błąd wątku: {e}")
                        with error_lock:
                            error_links.append(f"{current_url} | Błąd wątku: {type(e).__name__}: {e}")
            
            # Warunki zakończenia
            if to_visit.empty() and not futures:
                print("\n⚠️  Brak więcej linków do przetworzenia")
                break
            
            if len(visited) >= max_pages:
                print(f"\n⚠️  Osiągnięto limit {max_pages} stron")
                break
            
            time.sleep(0.01)

finally:
    # Zamknij pliki
    output_texts.close()
    output_links.close()

# ============================================================================
# PODSUMOWANIE CRAWLINGU
# ============================================================================
elapsed = time.time() - start_time

print(f"\n" + "="*60)
print(f"✅ CRAWLING ZAKOŃCZONY")
print(f"="*60)
print(f"⏱️  Czas: {elapsed:.2f}s ({elapsed/60:.1f} min)")
print(f"📊 Przetworzone strony: {len(visited)}")
print(f"🔗 Znalezione linki: {len(all_links)}")
print(f"❌ Błędów: {len(error_links)}")
print(f"⚡ Prędkość: {len(visited)/elapsed:.2f} stron/s")
print(f"="*60)

# ============================================================================
# ZAPIS BŁĘDÓW
# ============================================================================
if error_links:
    with open("error_links.txt", 'w', encoding='utf-8') as f:
        for error in sorted(error_links):
            f.write(error + '\n')
    print(f"\n❌ Błędy zapisano w: error_links.txt ({len(error_links)} błędów)")

# ============================================================================
# STATYSTYKI PLIKÓW
# ============================================================================
try:
    texts_size = os.path.getsize("teksty.txt") / (1024 * 1024)  # MB
    links_size = os.path.getsize("all_links.txt") / 1024  # KB
    
    print(f"\n💾 Zapisane pliki:")
    print(f"   📝 teksty.txt ({texts_size:.2f} MB)")
    print(f"   🔗 all_links.txt ({links_size:.1f} KB)")
    if error_links:
        errors_size = os.path.getsize("error_links.txt") / 1024  # KB
        print(f"   ❌ error_links.txt ({errors_size:.1f} KB)")
    
except:
    pass

print(f"\n🎉 CRAWLING GOTOWY!")
print(f"   ✅ Pomyślnie: {len(visited)}")
print(f"   ❌ Błędy: {len(error_links)}")
print(f"   🔗 Odkryte linki: {len(all_links)}")

# ============================================================================
# ============================================================================
# DEDUPLIKATOR - URUCHAMIA SIĘ AUTOMATYCZNIE
# ============================================================================
# ============================================================================

print("\n" + "="*60)
print("🧹 DEDUPLIKATOR TEKSTU")
print("="*60)

input_file = "teksty.txt"
output_file = "teksty_unikalne.txt"
dedup_separator = "_" * 50

print(f"\n📄 Źródło: {input_file}")
print(f"💾 Cel: {output_file}\n")

dedup_start_time = time.time()

# ============================================================================
# WCZYTAJ I PRZETWÓRZ
# ============================================================================
try:
    # Wczytaj plik
    print("📖 Wczytuję plik...")
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Podziel na sekcje
    sections = content.split(separator)
    
    # Usuń pustą sekcję na końcu (jeśli istnieje)
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
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, section in enumerate(processed):
            f.write(section)
            
            # Dodaj separator (oprócz ostatniej sekcji)
            if i < len(processed) - 1:
                if not section.endswith('\n'):
                    f.write('\n')
                f.write(dedup_separator + '\n')
    
    # Podsumowanie deduplikacji
    dedup_elapsed = time.time() - dedup_start_time
    removed = total_lines - total_unique
    
    print(f"\n" + "="*60)
    print(f"✅ DEDUPLIKACJA ZAKOŃCZONA")
    print(f"="*60)
    print(f"⏱️  Czas: {dedup_elapsed:.2f}s")
    print(f"📊 Sekcji: {len(sections)}")
    print(f"📝 Łącznie linii: {total_lines}")
    print(f"✅ Unikalne: {total_unique}")
    print(f"🗑️  Usunięte: {removed}")
    print(f"💾 Oszczędność: {(removed/total_lines*100):.1f}%")
    print(f"="*60)
    
    # Statystyka rozmiaru pliku
    try:
        unique_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
        print(f"\n💾 Plik wyjściowy:")
        print(f"   📝 teksty_unikalne.txt ({unique_size:.2f} MB)")
    except:
        pass

except FileNotFoundError:
    print(f"❌ Błąd: Plik '{input_file}' nie istnieje!")
except Exception as e:
    print(f"❌ Błąd deduplikacji: {e}")

# ============================================================================
# KOŃCOWE PODSUMOWANIE
# ============================================================================
total_elapsed = time.time() - start_time

print(f"\n" + "="*60)
print(f"🎉 WSZYSTKO GOTOWE!")
print(f"="*60)
print(f"⏱️  Całkowity czas: {total_elapsed:.2f}s ({total_elapsed/60:.1f} min)")
print(f"\n📦 PLIKI WYJŚCIOWE:")
print(f"   📝 teksty.txt - oryginalne teksty")
print(f"   🧹 teksty_unikalne.txt - teksty bez duplikatów")
print(f"   🔗 all_links.txt - wszystkie znalezione linki")
if error_links:
    print(f"   ❌ error_links.txt - błędy podczas crawlingu")
print(f"\n✨ Dziękuję za skorzystanie z crawlera!")
print(f"="*60)