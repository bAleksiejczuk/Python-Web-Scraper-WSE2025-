import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import queue

# ============================================================================
# KONFIGURACJA
# ============================================================================
print("="*60)
print("🕷️  WEB CRAWLER")
print("="*60)

url = input("\n📍 URL strony: ").strip()
if not url.startswith(('http://', 'https://')):
    url = 'https://' + url

max_pages = input("📊 Max stron (Enter = 1000): ").strip()
max_pages = int(max_pages) if max_pages else 1000

max_workers = input("🔧 Wątków (Enter = 10): ").strip()
max_workers = int(max_workers) if max_workers else 10

delay = input("⏱️  Opóźnienie między requestami w sekundach (Enter = 0.1): ").strip()
delay = float(delay) if delay else 0.1

# ============================================================================
# INICJALIZACJA
# ============================================================================
parsed_start = urlparse(url)
base_domain = parsed_start.netloc

# ✅ OBSŁUGA ALIASÓW DOMEN (www i bez www)
if base_domain.startswith('www.'):
    base_domain_alt = base_domain[4:]  # example.com
    allowed_domains = [base_domain, base_domain_alt]
else:
    base_domain_alt = 'www.' + base_domain  # www.example.com
    allowed_domains = [base_domain, base_domain_alt]

visited = set()
error_links = set()
all_links = set([url])
to_visit = queue.Queue()
to_visit.put(url)

visited_lock = Lock()
error_lock = Lock()
links_lock = Lock()

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

print(f"\n🚀 Start: {url}")
print(f"📍 Domeny: {', '.join(allowed_domains)}")
print(f"🔧 Wątków: {max_workers}")
print(f"📊 Limit: {max_pages}")
print(f"⏱️  Opóźnienie: {delay}s\n")

start_time = time.time()

# ============================================================================
# FUNKCJA POBIERANIA LINKÓW
# ============================================================================
def get_links(url):
    """Pobiera linki ze strony + zapisuje błędy"""
    
    # ✅ RATE LIMITING - opóźnienie przed requestem
    time.sleep(delay)
    
    try:
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        with error_lock:
            error_links.add(f"{url} | Błąd pobierania: {e}")
        return []
    
    # Sprawdź typ zawartości
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' not in content_type:
        with error_lock:
            error_links.add(f"{url} | Nie-HTML: {content_type}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    links = []
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        
        # Pomiń specjalne linki
        if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        
        try:
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            
            # Walidacja: musi mieć schemat i domenę
            if not parsed.scheme or not parsed.netloc:
                with error_lock:
                    error_links.add(f"{href} | Niepoprawny URL (brak schematu/domeny) | Źródło: {url}")
                continue
            
            # ✅ SPRAWDŹ CZY DOMENA JEST W ALLOWED_DOMAINS (www i bez www)
            if parsed.netloc not in allowed_domains:
                continue
            
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Pomiń pliki binarne
            if clean_url.lower().endswith(('.pdf', '.jpg', '.png', '.zip', '.doc', '.docx', '.xls', '.xlsx')):
                continue
            
            links.append(clean_url)
            
        except (ValueError, Exception) as e:
            with error_lock:
                error_links.add(f"{href} | Błąd parsowania: {e} | Źródło: {url}")
            continue
    
    return links

# ============================================================================
# FUNKCJA PRZETWARZANIA URL
# ============================================================================
def process_url(url):
    """Przetwarza pojedynczy URL"""
    # Sprawdź czy już odwiedzony
    with visited_lock:
        if url in visited:
            return []
        visited.add(url)
        visited_count = len(visited)
    
    with links_lock:
        all_links_count = len(all_links)
    
    print(f"🔍 [{visited_count}/{all_links_count}] {url}")
    
    # Pobierz linki
    new_links = get_links(url)
    
    # Dodaj nowe linki
    added = []
    with links_lock:
        for link in new_links:
            if link not in visited and link not in all_links:
                all_links.add(link)
                added.append(link)
        updated_count = len(all_links)
    
    if added:
        print(f"   ➕ +{len(added)} linków (razem: {updated_count})")
    
    return added

# ============================================================================
# GŁÓWNA PĘTLA CRAWLINGU
# ============================================================================
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
            for future in list(futures.keys()):
                if future.done():
                    current_url = futures.pop(future)
                    try:
                        new_links = future.result()
                        for link in new_links:
                            to_visit.put(link)
                    except Exception as e:
                        print(f"❌ Błąd przetwarzania {current_url}: {e}")
                        with error_lock:
                            error_links.add(f"{current_url} | Błąd wątku: {e}")
        
        # Sprawdź warunki zakończenia
        if to_visit.empty() and not futures:
            print("\n⚠️  Brak więcej linków")
            break
        
        if len(visited) >= max_pages:
            print(f"\n⚠️  Limit {max_pages} stron")
            break

# ============================================================================
# PODSUMOWANIE
# ============================================================================
elapsed = time.time() - start_time

print(f"\n" + "="*60)
print(f"✅ ZAKOŃCZONO")
print(f"="*60)
print(f"⏱️  Czas: {elapsed:.2f}s")
print(f"📊 Odwiedzono: {len(visited)} stron")
print(f"📝 Znaleziono: {len(all_links)} URLi")
print(f"⚠️  Błędów: {len(error_links)}")
print(f"⚡ Prędkość: {len(visited)/elapsed:.2f} stron/s")
print(f"="*60)

# ============================================================================
# ZAPIS DO PLIKÓW
# ============================================================================
with open("all_links.txt", 'w', encoding='utf-8') as f:
    for link in sorted(visited):
        f.write(link + '\n')
print(f"\n💾 Zapisano {len(visited)} linków do: all_links.txt")

if error_links:
    with open("error_links.txt", 'w', encoding='utf-8') as f:
        for link in sorted(error_links):
            f.write(link + '\n')
    print(f"⚠️  Błędy zapisano do: error_links.txt")

print(f"\n🎉 GOTOWE!")
print(f"   ✅ Poprawnych: {len(visited)}")
print(f"   ❌ Błędnych: {len(error_links)}")