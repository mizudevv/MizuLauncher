# MizuLauncher - lokalizacje i pobieranie

Biblioteka korzysta z lokalnego stanu instalacji. Przycisk „⚙ Lokalizacja” otwiera ustawienia konkretnej gry. Jeśli EXE nie jest wpisane, launcher automatycznie przeszukuje folder rekurencyjnie. W Ustawieniach globalnych przy folderze gier jest również przycisk ⚙ do wyboru folderu.

Opcje instalacji gry: `extract_to_game_folder`, `show_install_note`, `install_button_label` są zapisywane w katalogu gry i publikowane razem z katalogiem.

Jeśli hosting zwraca HTML/JSON zamiast ZIP-a, launcher zgłosi to jako błąd i poprosi o bezpośredni link do archiwum. Nie omija zabezpieczeń ani anty-botów zewnętrznych stron.
