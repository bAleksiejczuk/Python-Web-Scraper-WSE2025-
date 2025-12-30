import requests
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ============================================================================
# KONFIGURACJA
# ============================================================================
print("="*60)
print("📝 EKSTRAKTOR TEKSTU")
print("="*60)

input_file = input("\n📄 Plik z linkami (Enter = all_links.txt): ").strip()
input_file = input_file if input_file else "all_links.txt"

output_file = input("💾 Plik wyjściowy (Enter = teksty.txt): ").strip()
output_file = output_file if output_file else "teksty.txt"

max_workers = input("🔧 Wątków (Enter = 10): ").strip()
max_workers = int(max_workers) if max_workers else 10

delay = input("⏱️  Opóźnienie między requestami w sekundach (Enter = 0.5): ").strip()
delay = float(delay) if delay else 0.5

# ============================================================================
# INICJALIZACJA
# ============================================================================
separator = "_" * 50
write_lock = Lock()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

print(f"\n🚀 Rozpoczynam ekstrakcję...")
print(f"📄 Źródło: {input_file}")
print(f"💾 Cel: {output_file}")
print(f"🔧 Wątków: {max_workers}")
print(f"⏱️  Opóźnienie: {delay}s\n")

start_time = time.time()

# ============================================================================
# FUNKCJA POBIERANIA TEKSTU
# ============================================================================
def get_text_from_url(url):
    """Pobiera tekst ze strony"""
    
    # Opóźnienie
    time.sleep(delay)
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Usuń niewidoczne elementy
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
        
        return text
    
    except Exception as e:
        return f"BŁĄD PODCZAS POBIERANIA STRONY: {str(e)}"

# ============================================================================
# FUNKCJA PRZETWARZANIA LINKU
# ============================================================================
def process_link(link, index, total):
    """Przetwarza pojedynczy link"""
    print(f"🔍 [{index}/{total}] {link}")
    text = get_text_from_url(link)
    return link, text

# ============================================================================
# WCZYTAJ LINKI
# ============================================================================
try:
    with open(input_file, 'r', encoding='utf-8') as f:
        links = [line.strip() for line in f if line.strip()]
    
    total_links = len(links)
    print(f"📋 Znaleziono {total_links} linków\n")

except FileNotFoundError:
    print(f"❌ Błąd: Plik '{input_file}' nie istnieje!")
    exit(1)

# ============================================================================
# PRZETWARZANIE WIELOWĄTKOWE
# ============================================================================
with open(output_file, 'w', encoding='utf-8') as out_file:
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Uruchom wszystkie zadania
        futures = {
            executor.submit(process_link, link, i+1, total_links): link 
            for i, link in enumerate(links)
        }
        
        # Zbieraj wyniki
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                link, text = future.result()
                
                # Zapisz do pliku
                with write_lock:
                    out_file.write(f"{link}\n\n")
                    out_file.write(f"{text}\n\n")
                    out_file.write(f"{separator}\n\n")
                    out_file.flush()
                
                print(f"✅ [{completed}/{total_links}] Zapisano")
                
            except Exception as e:
                link = futures[future]
                print(f"❌ Błąd: {link} - {e}")

# ============================================================================
# PODSUMOWANIE
# ============================================================================
elapsed = time.time() - start_time

print(f"\n" + "="*60)
print(f"✅ ZAKOŃCZONO")
print(f"="*60)
print(f"⏱️  Czas: {elapsed:.2f}s")
print(f"📊 Przetworzone: {total_links} linków")
print(f"⚡ Prędkość: {total_links/elapsed:.2f} linków/s")
print(f"="*60)
print(f"\n💾 Wyniki zapisano w: {output_file}")
print(f"🎉 GOTOWE!")