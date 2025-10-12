import re


def fix_ts_file(filename):
    """Исправляет файл .ts, удаляя лишние закрывающие теги </message>."""
    # Чтение содержимого файла
    with open(filename, encoding='utf-8') as f:
        content = f.read()
    
    # Подсчет исходных тегов
    message_start_count = len(re.findall(r'<message>', content))
    message_end_count = len(re.findall(r'</message>', content))
    
    print(f"Исходное количество тегов <message>: {message_start_count}")
    print(f"Исходное количество тегов </message>: {message_end_count}")
    
    # Удаление дублирующихся закрывающих тегов </message>
    # Ищем и удаляем два подряд идущих закрывающих тега </message>
    while '</message>\n    </message>' in content:
        content = content.replace('</message>\n    </message>', '</message>')
    
    # Также проверим другие варианты форматирования
    while '</message>\n</message>' in content:
        content = content.replace('</message>\n</message>', '</message>')
    
    while '</message>\n\n</message>' in content:
        content = content.replace('</message>\n\n</message>', '</message>')
    
    # Подсчет тегов после исправления
    message_start_count_after = len(re.findall(r'<message>', content))
    message_end_count_after = len(re.findall(r'</message>', content))
    
    print(f"Количество тегов <message> после исправления: {message_start_count_after}")
    print(f"Количество тегов </message> после исправления: {message_end_count_after}")
    
    # Запись исправленного содержимого обратно в файл
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Файл {filename} успешно исправлен!")
    
    # Проверка на баланс тегов
    if message_start_count_after == message_end_count_after:
        print("Теги сбалансированы. Файл корректен для компиляции lrelease.")
    else:
        print(f"ВНИМАНИЕ: Несбалансированные теги. <message>: {message_start_count_after}, </message>: {message_end_count_after}")

if __name__ == "__main__":
    fix_ts_file("app_de.ts")
