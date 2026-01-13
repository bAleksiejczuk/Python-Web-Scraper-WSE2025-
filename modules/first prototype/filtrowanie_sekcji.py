def filter_duplicate_lines_by_section(input_file, output_file):
    # Separator sekcji
    separator = "__________________________________________________"
    
    try:
        # Wczytaj cały plik
        with open(input_file, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Sprawdź, czy plik zaczyna się od separatora
        starts_with_separator = content.lstrip().startswith(separator)
        
        # Podziel zawartość na sekcje, z zachowaniem separatora
        sections_with_separators = []
        if starts_with_separator:
            # Jeśli plik zaczyna się od separatora, dodaj pusty element na początku
            sections_with_separators.append("")
        
        # Podziel zawartość na sekcje
        sections = content.split(separator)
        
        # Przetwarzaj każdą sekcję
        processed_sections = []
        total_lines = 0
        total_unique_lines = 0
        
        for i, section in enumerate(sections):
            # Jeśli jest to ostatni element i jest pusty, przerwij
            if i == len(sections) - 1 and not section.strip():
                break
                
            # Podziel sekcję na linie
            lines = section.split('\n')
            
            # Zachowaj unikalne linie w oryginalnej kolejności
            unique_lines = []
            seen_lines = set()
            
            for line in lines:
                total_lines += 1
                if line not in seen_lines:
                    seen_lines.add(line)
                    unique_lines.append(line)
                    total_unique_lines += 1
            
            # Dodaj przetworzoną sekcję
            processed_sections.append('\n'.join(unique_lines))
        
        # Łączymy sekcje z separatorem, zachowując odpowiednie formatowanie
        with open(output_file, 'w', encoding='utf-8') as file:
            for i, section in enumerate(processed_sections):
                # Zapisz zawartość sekcji
                file.write(section)
                
                # Dodaj separator po każdej sekcji oprócz ostatniej
                if i < len(processed_sections) - 1:
                    # Upewnij się, że między sekcją a separatorem jest nowa linia
                    if not section.endswith('\n'):
                        file.write('\n')
                    
                    # Dodaj separator w nowej linii
                    file.write(separator)
                    file.write('\n')
        
        # Wyświetl statystyki
        duplicates_removed = total_lines - total_unique_lines
        print(f"Wczytano łącznie: {total_lines} linii.")
        print(f"Po usunięciu duplikatów: {total_unique_lines} unikalnych linii.")
        print(f"Usunięto {duplicates_removed} zduplikowanych linii.")
        print(f"Wynik zapisano w pliku '{output_file}'")
    
    except FileNotFoundError:
        print(f"Błąd: Plik '{input_file}' nie został znaleziony.")
    except Exception as e:
        print(f"Wystąpił błąd: {e}")

def main():
    input_file = "teksty.txt"
    output_file = "teksty_unikalne.txt"
    
    filter_duplicate_lines_by_section(input_file, output_file)

if __name__ == "__main__":
    main()