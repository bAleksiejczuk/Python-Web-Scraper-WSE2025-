import time

# ============================================================================
# KONFIGURACJA
# ============================================================================
input_file = "teksty.txt"
output_file = "teksty_unikalne.txt"
separator = "_" * 50

print("="*60)
print("🧹 DEDUPLIKATOR TEKSTU")
print("="*60)
print(f"\n📄 Źródło: {input_file}")
print(f"💾 Cel: {output_file}\n")

start_time = time.time()

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
                f.write(separator + '\n')
    
    # Podsumowanie
    elapsed = time.time() - start_time
    removed = total_lines - total_unique
    
    print(f"\n" + "="*60)
    print(f"✅ ZAKOŃCZONO")
    print(f"="*60)
    print(f"⏱️  Czas: {elapsed:.2f}s")
    print(f"📊 Sekcji: {len(sections)}")
    print(f"📝 Łącznie linii: {total_lines}")
    print(f"✅ Unikalne: {total_unique}")
    print(f"🗑️  Usunięte: {removed}")
    print(f"💾 Oszczędność: {(removed/total_lines*100):.1f}%")
    print(f"="*60)
    print(f"\n🎉 GOTOWE!")

except FileNotFoundError:
    print(f"❌ Błąd: Plik '{input_file}' nie istnieje!")
except Exception as e:
    print(f"❌ Błąd: {e}")