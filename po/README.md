# Localization for ChromeOS Factory Software

This folder contains translated resources for labels and messages used in
ChromeOS factory software, in
[GNU gettext](https://www.gnu.org/software/gettext/) format.

## Usage

There are several different scenarios that would involve text translations.
This shows the workflow for each scenario.

### Modifying code in public repository
1. Write codes, and mark text that need to be translated by
   `_("Translatable text")`.
   For static HTML, use `i18n-label` tag for text that needs to be translated.
2. Run `make update` inside this directory.
3. Edit `${LOCALE}.po`.
   For each new / changed text, translate them accordingly inside the `.po`
   file.
4. Commit the code changes together with `.po` file changes.

### Modifying code in board overlay
1. Write codes, and mark text that need to be translated by
   `_("Translatable text")`.
   For static HTML, use `i18n-label` tag for text that needs to be translated.
2. Run `make update BOARD=board` inside this directory.
3. Edit `po/${LOCALE}.po` **in board overlay**.
   For each new / changed text, translate them accordingly inside the `.po`
   file.
4. Commit the code changes together with `.po` file changes.

### Adding translations for a new locale in public repository
1. Run `make init LOCALE=xx-YY` inside this directory,
   where `xx-YY` is the new locale to be translated to. (e.g. `zh-CN`).
2. A new `xx-YY.po` would be generated. Edit the file and add translations.
3. Commit the new `.po` file.

### Adding translations for a locale that exists in public repository into board overlay
1. Run `make update BOARD=board` inside this directory.
2. Edit `po/${LOCALE}.po` **in board overlay** and add translations.
   The `.po` file would only contain text extracted from files in board overlay.
3. Commit the new `.po` file.

### Adding translations for a new locale that would only exist in board overlay
1. Run `make init BOARD=board LOCALE=xx-YY` inside this directory , where
   `xx-YY` is the new locale to be translated to. (e.g. `zh-CN`).
2. A new `po/xx-YY.po` would be generated **in board overlay**, which would
   contains all text extracted from both public repository and board overlay.
   Edit the file and add translations.
3. Commit the new `.po` file.
