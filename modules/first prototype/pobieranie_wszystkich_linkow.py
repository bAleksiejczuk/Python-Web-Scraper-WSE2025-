import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def get_links(url):
    # Pobierz stronę
    try:
        response = requests.get(url)
        response.raise_for_status()  # Sprawdź czy nie ma błędów
    except requests.exceptions.RequestException as e:
        print(f"Błąd podczas pobierania strony: {e}")
        return []
    
    # Sparsuj HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Uzyskaj domenę główną strony
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc
    
    # Znajdź wszystkie linki
    links = []
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # Przekształć względne URL w pełne URL
        full_url = urljoin(url, href)
        # Sprawdź, czy link jest związany z tą samą domeną
        parsed_link = urlparse(full_url)
        if parsed_link.netloc == base_domain or not parsed_link.netloc:
            links.append(full_url)
    
    return links

def save_links_to_file(links, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        for link in links:
            file.write(link + '\n')

def main():
    # Poproś użytkownika o podanie URL strony głównej
    url = input("Podaj url")
    
    # Pobierz linki
    print(f"Pobieram linki ze strony {url}...")
    links = get_links(url)
    
    # Zapisz linki do pliku
    filename = "links.txt"
    save_links_to_file(links, filename)
    
    print(f"Znaleziono {len(links)} linków i zapisano je w pliku '{filename}'")

if __name__ == "__main__":
    main()