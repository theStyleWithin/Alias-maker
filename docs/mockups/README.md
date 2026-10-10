# Mockups

These pictures show what Alias Maker is meant to look like on a CachyOS PC (KDE Plasma, Breeze dark). They're **mockups drawn from the code, not screenshots**: Alias Maker hasn't been run on a real PC yet, and the PC details in them (user name, hardware, drive list) are made up. The wording on screen is the app's real wording. Once Alias Maker runs on real hardware, these should be swapped for real screenshots.

Each picture, what it shows, and where that part lives in the code:

| Picture | What it shows | Where it's explained | In the code |
|---|---|---|---|
| [welcome.png](welcome.png) | A new window: big DOIT, the PC's info (Terminal: aliasmaker, Shell: fish), the Let'sdostuff~ prompt | [README](../../README.md#what-it-is), [DESIGN: The DOIT welcome](../DESIGN.md) | `fish_greeting` in `src/shell/lets-do-stuff.fish`; `welcome_text`, `fastfetch_command` in `src/aliasmaker_core.py`; logo in `src/shell/doit-logo.txt` |
| [menu.png](menu.png) | The ☰ menu with Custom Commands opening to the side, like Konsole | [README](../../README.md#what-it-is), [DESIGN: the ☰ menu](../DESIGN.md) | `TerminalWindow.build_menu`, `refresh_menu` in `src/aliasmaker` |
| [database.png](database.png) | ☰ → Database, searching "drives": lsblk first, best matches on top | README: Database, [DESIGN: Database window, Search](../DESIGN.md) | `DatabaseWindow` in `src/aliasmaker`; `search_library`, `COMMON_PICKS` in `src/aliasmaker_core.py` |
| [custom-commands.png](custom-commands.png) | ☰ → Custom Commands → Custom Command List: your commands in an editable table | README: Custom Commands, DESIGN: Custom Commands window | `CustomWindow` in `src/aliasmaker` |
| [create-command.png](create-command.png) | Create Command, offering one-word names for a name with spaces | README: Create Command, DESIGN: Create/Edit dialog | `CommandDialog` in `src/aliasmaker`; `name_suggestions` in `src/aliasmaker_core.py` |
| [delete-command.png](delete-command.png) | Delete Command: only the alias is deleted, never the real program | README: Deleting a command, DESIGN: Delete dialog | `DeleteDialog` in `src/aliasmaker`; `remove_custom_command` in `src/aliasmaker_core.py` |
| [terminal-settings.png](terminal-settings.png) | ☰ → Terminal Settings: the command log switch and how to say yes | README: Terminal Settings, DESIGN: Terminal Settings window | `SettingsWindow` in `src/aliasmaker` |
| [command-log.png](command-log.png) | View Command Log: what ran and whether it worked | README: Terminal Settings, DESIGN: Command Log window | `LogWindow` in `src/aliasmaker`; `log_result`, `read_log` in `src/aliasmaker_core.py` |
| [doit-create.png](doit-create.png) | `doit create` in the terminal: picking `check-drives`, then using it right away in the same window | [README: Your commands are real terminal commands](../../README.md#your-commands-are-real-terminal-commands), DESIGN: Real terminal commands | `add_custom`, `pick_name`, `write_fish_shortcuts` in `src/aliasmaker_core.py`; `__aliasmaker_reload_shortcuts` in `src/shell/lets-do-stuff.fish` |
| [clippy-typing.png](clippy-typing.png) | Typing `/clippy`: white, not red, and it becomes `doit clippy` when you press space | README: /clippy, DESIGN: /clippy | the `abbr` line in `src/shell/lets-do-stuff.fish` |
| [clippy.png](clippy.png) | `/clippy chrooting`: CachyOS wiki, Arch Wiki and manual page results | README: /clippy, DESIGN: /clippy | `clippy`, `search_wiki`, `search_arch_wiki` in `src/aliasmaker_core.py` |
