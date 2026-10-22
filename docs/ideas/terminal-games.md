# Terminal games: `/play` (parked idea, not built)

Status: an idea the author likes, parked until the author has scanned and tested the current
AppImage candidates and Alias Maker is released as "complete". A rough prototype was shown
(`docs/mockups/terminal-game-prototype.png`); it lived in a scratch copy and was never committed.

## The idea
Alias Maker is the console, a game is a cartridge: one small text file. `/play` lists the cartridges
on the PC and starts one only when the player picks it and confirms. In a game, the player reads
stage directions from a theatrical script and answers each with the real command that performs it
("The Knight shouts the word bash!" -> `echo bash!`). Nothing the player types is ever run.

Original example: **Shell Knights** vs the **Root Lord** (original names on purpose; the author's
first idea was a Star Wars duel, but those names are Lucasfilm's).

## Rules (the author's)
- Games are **data, never code**. Nothing typed in a game reaches a shell; no `subprocess`, no `eval`.
- Game mode must look different from the terminal, like the AI chat does: its own title, banner and a
  `GAME ❯` prompt that a cartridge can't change.
- **Starts only when picked** (a menu, then a yes). Cartridges from outside get "from your games
  folder, made by someone else. Start it?".
- **Alias Maker ships only original games.** Franchise fan games, if anyone makes them, come from their
  authors, not from this project: don't host, list or promote them (README and docs say so, with a
  contact for removal requests). The author isn't a lawyer; if this grows, ask one.
- Keep the first version small: `/play`, the menu, one game, a strict loader, tests.

## Safety (to put in the spec)
- Plain-data parser with limits (file size, scenes, line length, nesting); refuse anything over.
- Clean every cartridge text like AI replies (strip escape codes, cursor moves, title changes).
- Answers limited to a short list of harmless commands (echo, ls, cd, pwd, cat...); lessons that
  mention dangerous commands (rm -rf, curl | sh, dd, mkfs, sudo...) get a visible warning or the
  cartridge is refused. No password prompts; input is always visible.
- Only read the games folder (no symlinks out of it); saves go in the game's own spot; no network, no links.
- **Hostile test inputs are generated in memory by the tests, never stored as files** (the author
  doesn't want malicious-looking files in the repo while fighting antivirus false positives).

## Cartridge sketch (format not final)
```
title:    Shell Knights
by:       Alias Maker (original)
act 1: The Duel
  say:   Root Lord | Join me, and rule the whole filesystem!
  say:   You       | I will never join you!!!
  scene:
    direction: The Knight shouts the word "bash!" across the arena.
    answer:    echo bash!
    hint1:     Which command makes the computer say words?
    learn:     echo = speak words aloud
```

## Order of work, when the author says go
1. Settle the antivirus scan and release 1.5.2 (see CLAUDE.md, Antivirus).
2. Write the cartridge spec (with the safety section) for the author to review.
3. Build the small first version of `/play`, with tests.
4. Release it as a normal update.
