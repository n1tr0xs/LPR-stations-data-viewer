Эта программа создана для отображения данных, поступающих со станций и постов РосГидроМет.
В файле settings.ini хранятся настройки программы.
Список серверов, станций/постов, промежуток обновления информации.

Как пользоваться settings.ini:
1. Блок [сервера].
Список серверов в формате "<название сервера> = <адрес сервера>".
название сервера можно задать произвольное, оно используется только в следующих разделах файла для разделения станций и постов по серверам.

2. Блоки станций.
Для каждого сервера создается свой блок со списком станций/постов.
[<название сервера>]
<индекс> = <название>
...

<название> может быть произвольным и используется только для названия столбца с данными с этой станции/поста.

3. Блок единицы.
В этом блоке указываются желаемые единицы измерения для получаемых с сервера.
Например, если получаем Кельвины, и хотим видеть Цельсий - "k = C"

4. Блок настройки.
В этом блоке указываются дополнительные настройки программы.
*период - периодичность обновления данных (не рекомендуется ставить меньше 15 секунд).

---
Сборка исходного когда (необходимы `Python >=3.11`, `pyinstaller`):
```
REM Обновление pip
python -m pip install --upgrade pip
REM Установка зависимостей
pip install -r requirements.txt
pip install pyinstaller
REM Сборка приложения
pyinstaller --noconfirm --clean --log-level FATAL --onedir --name "LPR stations data viewer" --contents-directory "." --noconsole --icon "icon.ico" --add-data "icon.ico";"." --add-data "settings.ini";"." "main.py"
```



