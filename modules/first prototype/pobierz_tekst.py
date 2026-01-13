import requests
from bs4 import BeautifulSoup
import time

def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parsuj HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Usuń tagi script, style, head i inne niewidoczne elementy
        for element in soup(['script', 'style', 'head', 'title', 'meta', 'iframe', 'noscript']):
            element.extract()
        
        # Zastąp tagi, które odpowiadają za formatowanie, odpowiednimi znakami
        for br in soup.find_all('br'):
            br.replace_with('\n')
        
        for p in soup.find_all('p'):
            p.append(soup.new_string('\n\n'))
        
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            h.append(soup.new_string('\n\n'))
        
        for li in soup.find_all('li'):
            li.insert(0, soup.new_string('• '))
            li.append(soup.new_string('\n'))
        
        # Pobierz cały tekst z dokumentu
        text = soup.get_text()
        
        # Usuń nadmiarowe białe znaki, zachowując formatowanie
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        
        return text
    
    except Exception as e:
        return f"BŁĄD PODCZAS POBIERANIA STRONY: {str(e)}"

def process_links_file(input_file, output_file):
    """Przetwarza plik z linkami i zapisuje teksty do pliku wyjściowego"""
    separator = "_" * 50
    
    try:
        # Wczytaj linki
        with open(input_file, 'r', encoding='utf-8') as file:
            links = [line.strip() for line in file if line.strip()]
        
        # Otwórz plik wyjściowy
        with open(output_file, 'w', encoding='utf-8') as out_file:
            total_links = len(links)
            
            for i, link in enumerate(links, 1):
                print(f"Przetwarzanie linku {i}/{total_links}: {link}")
                
                # Pobierz tekst ze strony
                text = get_text_from_url(link)
                
                # Zapisz link i tekst do pliku
                out_file.write(f"{link}\n\n")
                out_file.write(f"{text}\n\n")
                out_file.write(f"{separator}\n\n")
                
                # Krótkie opóźnienie między zapytaniami
                time.sleep(1)
        
        print(f"\nPrzetwarzanie zakończone. Pobrano teksty z {total_links} stron.")
        print(f"Wyniki zapisano w pliku '{output_file}'")
    
    except FileNotFoundError:
        print(f"Błąd: Plik '{input_file}' nie został znaleziony.")
    except Exception as e:
        print(f"Wystąpił nieoczekiwany błąd: {e}")

def main():
    input_file = "links.txt"
    output_file = "teksty.txt"
    
    process_links_file(input_file, output_file)

if __name__ == "__main__":
    main()