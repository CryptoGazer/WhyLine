# WhyLine Plugin — Local Deploy Guide (Variant A)

Вариант для хакатона и демо: установка `.zip` напрямую в IntelliJ IDEA без публикации на Marketplace.

---

## Разовая установка (первый раз)

### 1. Узнать путь к папке плагинов своей IDE

Открой IntelliJ IDEA и выполни:

```
Help → About → Show in Finder (macOS) / Show in Explorer (Windows)
```

Или найди папку вручную:

| ОС | Путь |
| --- | --- |
| macOS | `~/Library/Application Support/JetBrains/IntelliJIdea<VERSION>/plugins` |
| Windows | `%APPDATA%\JetBrains\IntelliJIdea<VERSION>\plugins` |
| Linux | `~/.local/share/JetBrains/IntelliJIdea<VERSION>/plugins` |

Пример для macOS 2024.3: `/Users/cryptogazer/Library/Application Support/JetBrains/IntelliJIdea2024.3/plugins`

### 2. Прописать путь в gradle.properties

Открой [plugin/gradle.properties](../plugin/gradle.properties), раскомментируй и отредактируй последнюю строку:

```properties
localIdePluginsDir=/Users/cryptogazer/Library/Application Support/JetBrains/IntelliJIdea2024.3/plugins
```

Нажми **Load Gradle Changes** (всплывёт в правом нижнем углу IntelliJ).

### 3. Первая сборка и установка

В Gradle tool window (правая панель) запусти:

```
Tasks → whyline → deployToLocalIde
```

Или из терминала (если есть Gradle wrapper):

```bash
cd plugin
./gradlew deployToLocalIde
```

### 4. Перезапустить IDE

```
File → Invalidate Caches → Just Restart
```

После перезапуска плагин WhyLine будет виден в `Settings → Plugins → Installed`.

---

## Каждое последующее изменение (быстрый путь)

После первой установки для обновления плагина **не нужно** качать zip и устанавливать через UI заново.

### Способ А — перезапуск (30 секунд)

1. Запусти `deployToLocalIde` из Gradle panel (одна кнопка)
2. `Help → Find Action → "Reload Plugin from Disk"` — IntelliJ перезагружает плагин **без полного рестарта**

> Если `Reload Plugin from Disk` не помогает (редкие случаи с изменением `plugin.xml`) — сделай `File → Invalidate Caches → Just Restart`.

### Способ Б — sandbox для разработки (рекомендуется во время итераций)

Пока пишешь код, **не устанавливай в основную IDE**. Используй встроенный sandbox:

```
Gradle panel → Tasks → intellij → runIde
```

Запускается вторая копия IntelliJ с установленным плагином. Изменения применяются пересборкой + перезапуском `runIde`. Основная IDE не трогается.

**Переключение на основную IDE нужно только перед финальным демо.**

---

## Полный цикл для демо-дня

```bash
# 1. Убедиться, что бэкенд запущен
cd backend && uvicorn app.main:app --port 8000

# 2. Собрать и установить плагин в основную IDE
#    (из Gradle panel или терминала)
cd plugin
./gradlew deployToLocalIde

# 3. В IntelliJ IDEA:
#    Help → Find Action → "Reload Plugin from Disk"
#    (или File → Invalidate Caches → Just Restart)

# 4. Настроить плагин:
#    Settings → Tools → WhyLine
#    Backend URL: http://localhost:8000
#    Workspace ID: 1, Repository ID: 1
```

---

## Gradle wrapper (если ./gradlew не работает)

Если `./gradlew` отсутствует, используй Gradle panel прямо в IntelliJ IDEA — она видит все задачи без wrapper. Либо создай wrapper один раз:

```bash
# Если gradle установлен глобально:
cd plugin && gradle wrapper --gradle-version 8.10

# Если не установлен — открой plugin/ в IntelliJ IDEA,
# она предложит создать wrapper автоматически при открытии build.gradle.kts
```

---

## Структура файлов плагина

```
plugin/
  src/main/resources/
    META-INF/plugin.xml          — манифест, регистрация сервисов и actions
    icons/whyline.svg            — иконка (Tool Window + Plugin Manager)
  src/main/kotlin/com/whyline/plugin/
    actions/ExplainWhyAction.kt  — точка входа (правый клик)
    services/GitContextService.kt — git blame/log через CLI
    services/BackendClient.kt    — HTTP-клиент к FastAPI
    toolwindow/WhyPanel.kt       — UI результата
    settings/WhySettings.kt      — персистентные настройки
    settings/WhySettingsConfigurable.kt — Preferences UI
    settings/WhyCredentialService.kt    — JetBrains Password Safe
```

---

## Что значат ошибки в VS Code

Красные подчёркивания `Unresolved reference: AnAction`, `Unresolved reference: intellij` и т.п. — это **ложные срабатывания** Kotlin Language Server в VS Code. KLS не имеет IntelliJ Platform SDK на classpath.

**Gradle-компиляция работает корректно.** Для разработки плагина используй IntelliJ IDEA — там все ссылки резолвятся правильно.
