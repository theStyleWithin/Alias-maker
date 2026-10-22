# Idea: Alias Maker for Android, a pocket terminal trainer (parked)

Status: **an idea only. Nothing is built and nothing starts until the author says go.**
The author wants to finish testing the AppImages and the virus scans first. The terminal games idea (`terminal-games.md`) comes before this one or alongside it.

## What it is

An Android app for people who like to dabble with the terminal. It is a **toy and a daily practice tool**, not a way to run a computer from a phone.

- Everything that happens in the app stays inside the app's own pretend shell.
- A "forcefield" keeps every command away from the real phone.
- Short daily practice: a small lesson, a few things to type, a streak, a friendly finish.

## What it is not

- Not a real terminal for the phone. It does not run Android's shell, Termux or any program on the device.
- Not for managing a PC from the phone (no SSH, no remote control).
- Not an AI app. The Alias Maker idea of plain words turning into real commands still applies, but here the "real command" only ever runs inside the pretend shell.

## The forcefield (the main rule)

The safest forcefield is one where there is **nothing real to escape to**. So the first plan is a *simulated* shell, not a real one in a cage.

- The pretend shell is code inside the app that understands a small set of commands (`ls`, `cd`, `cat`, `mkdir`, `cp`, `mv`, `rm`, `echo`, `grep`, `pwd`, `touch`, `man`-style help, a few more) and acts on a **pretend file system held in memory**.
- No command ever starts a real process. No `exec`, no `ProcessBuilder`, no shell on the phone.
- No access to the phone's files, contacts, camera, microphone, location or storage. The app asks for **no permissions**.
- No network needed. It works offline. (If an AI helper is ever added here it would be optional and off by default, with the same rules as on the PC.)
- "Dangerous" commands (`rm -rf /`, `sudo`, `dd`, fork bombs) are a *lesson*: the pretend shell reacts the way the real one would and explains why, but only the pretend file system is affected. A "reset the pretend computer" button always brings it back.
- Nothing is saved except progress (lesson done, streak). The pretend file system can be reset every session.
- Cartridge files (if shared with `/play`) are data only: nothing in them is ever run.

Why not a real shell inside a sandbox (proot, a Linux container)? It teaches more truthfully, but it is heavier, depends on the phone, and "contained" would be a promise we would have to keep against every Android version. A simulated shell has a much smaller surface to get wrong, which fits "safe and never scary". Revisit only if the author wants it.

## What a day looks like

1. Open the app. It greets you and shows today's tiny lesson ("Today: moving around with `cd`").
2. A few guided steps in the pretend shell, with plain-words hints, same friendly tone as Alias Maker.
3. A small challenge ("find the file named notes and show what is inside").
4. Done: streak goes up, tomorrow's topic is shown.

Ideas for later: typo helper ("did you mean?") just like the PC version; a "what does this command do" explainer; the terminal games as another mode (cartridges are the same format).

## Open questions for the author

- Name: "Alias Maker" for phones, or its own name so nobody mistakes it for the PC app?
- Build with Kotlin and Android's own toolkit, or reuse the Python engine somehow? (Probably Kotlin: a small pretend shell is easy to write there and keeps the app light.)
- Where to publish: GitHub release APK only, or a store (stores have their own review rules; the author avoided AUR and Flathub for that reason).
- Which commands come first, and in what order are the lessons?
- Same cartridge format as `/play`, so one game works on both?

## Order of work (when told to go)

1. Short spec with a safety section, like the games one, for the author to approve.
2. Pretend shell and pretend file system with tests (no real process or file access, checked by test).
3. A first handful of lessons.
4. A rendered mock-up of the screen for the author to approve before any app code.
5. Android app shell, then test on a real phone with the author.
