# Alias Maker: design notes

This repo holds the `doit` terminal wrapper and the alias maker on top of it. It was split out of [Doit-os](https://github.com/theStyleWithin/Doit-os) so the tool can be built and proven on a regular CachyOS install first. If it's stable there, it becomes Do It OS's selling point; if the distro never ships, this tool still stands on its own.

## Status

| Part | Status |
|---|---|
| Wrapper: plain-English phrases run real commands | Built (`src/doit`) |
| "Do what? I am waiting..." prompt | Built |
| Third-party install flow (show source URL, ask first) | Built |
| Command logging (asked once, toggle later, history) | Built |
| Yes-word settings (easy / strict / custom) | Built |
| Alias maker (user picks their own phrases) | **Next** |
| Bare phrases without the `doit` prefix | Later, optional |

Tested in a Linux sandbox only so far, not yet on CachyOS or the fish shell.

## Wrapper

- Typed with the `doit` prefix: `doit turn off`. Typing `doit` alone doesn't run anything, since the computer doesn't know what you want yet. It asks "Do what? I am waiting..." and keeps waiting (blank lines and unknown phrases ask again; "never mind" or Ctrl-D leaves).
- Matches exact phrases from the command index. Casual typing is tolerated: capitals, extra spaces, trailing `!`/`?`, and a "please".
- Unknown phrases get "Did you mean" suggestions but never run on a guess.
- Always shows the real command before running it.
- Translation works whether or not logging is on.

## Third-party install flow

For apps like Brave, the wrapper calls the vendor's own official install command instead of reimplementing it. Before running it:

1. Show the full source URL, highlighted.
2. Say plainly that this is the vendor's official installer, not something changed by Do It.
3. Show any warning, then ask for confirmation.

Piping a remote script into a shell trusts that URL on every run, so the URL is always shown and the run is logged (when logging is on).

## Settings

- **Command logging:** asked once, the first time `doit` runs a command. Saying no still translates commands; it only skips the log file. `doit logging on|off` changes it later, and logging starts from when it's turned on. `doit show me what you did` shows the history.
- **Yes wording:** by default both `y` and `yes` work. `doit answer strict` requires the full word; `doit answer word <word>` sets a custom one.

## Alias maker (next)

The user browses the command index and picks their own phrase for any command, including profane or silly ones, with no content restrictions. The alias stays linked to the original command.

- A command can have several aliases at once.
- Collisions with existing phrases warn; nothing is silently overwritten.
- Aliases are stored in the user's own settings, separate from the shipped index, so an update to the index never wipes them.
- Special shell characters (`!`, `$`, backticks, `;`, `|`, `&`) are handled automatically so a phrase works as typed. CachyOS uses the fish shell by default, which quotes differently from bash, so both need testing.
- Giving a system program a second name (for example `bash`) adds a link beside the original and never renames the original, because many scripts depend on the real name.
- Alias packs could eventually be exported and shared.

## Command index

`data/commands.json` is the single source of truth for the wrapper, the alias maker, a future help tray app, and the companion book. Each entry has:

| Field | Meaning |
|---|---|
| `id` | stable identifier |
| `category` | grouping for browsing |
| `phrases` | default plain-English triggers |
| `command` | the real command that runs |
| `explanation` | plain-English description |
| `needs_root` | whether it needs elevated rights |
| `confirm` | whether to ask before running |
| `source_url` | for third-party installers, the vendor URL shown before running |
| `warning` | optional plain-English caution shown before running |

The seed entries are drafts. Verify each against the book before relying on it.

## Open questions

- **Matching strictness:** stay with exact phrases, or add loose keyword matching?
- **Teaching moments:** show the real command every time, or only the first few times a phrase is used?
- **Brave entry:** Brave's installer falls back to an AUR helper and runs `pacman -Sy --noconfirm` when Brave isn't in the regular repos. The wrapper warns about this; a better approach is still needed.
