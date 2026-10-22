# Idea: Alias Maker for Android, a pocket terminal trainer (parked)

Status: **an idea only. Nothing is built and nothing starts until the author says go.**
The author wants to finish testing the AppImages and the virus scans first. The terminal games idea (`terminal-games.md`) is part of this app too.

## Decisions so far (from the author)

- Name: **Alias Maker** (same name as the PC app).
- Publishing: first a **GitHub release APK**. F-Droid is a realistic later step. Google Play is possible but unlikely.
- **Terminal games are a feature** of this app (`/play`, cartridge text files, nothing typed ever reaches the shell; see `terminal-games.md`).
- **Every command should work**, inside a hardened container, so that nothing runs on the phone itself. (This replaces the first plan of a small pretend shell; see "Why not a pretend shell" below.)

## The rule (the author's)

**Only the Android version is an emulator/simulator. It is never a real terminal on the phone.** The PC app (AppImage, installer, packages) stays a real terminal. Nothing typed in the Android app is ever run by the phone itself, and no feature, shortcut or "just this once" exception may change that. Anything that would need the phone to run a program (Plan B below included) needs the author's explicit yes first.

## What it is

An Android app for people who like to dabble with the terminal. It is a **toy and a daily practice tool**, not a way to run a computer from a phone.

- A real tiny Linux with a real shell, so every command behaves the way it does on a PC.
- It lives inside a sealed box. Whatever you do in there stays in there, and a "start fresh" button brings it back to new.
- Short daily practice: a small lesson, a few things to type, a streak, a friendly finish, plus the games.

## What it is not

- Not a terminal for the phone itself. It cannot see, change or run anything on the phone.
- Not for managing a PC from the phone (no SSH out, no remote control).
- Not an AI app. (An AI helper, if ever added here, is optional and off by default with the same rules as on the PC.)

## The forcefield: the main rule

"Nothing runs on your Android" has to be true in the strict sense, so the preferred plan is **an emulated computer, not a program started on the phone**.

Plan A (preferred): **a small emulated Linux computer** (a CPU emulator written into the app, running a tiny Linux image shipped inside the APK).
- The Linux programs are only ever *data the emulator reads*. The phone's CPU never runs them as programs, so there is no native process, no `exec`, and no way to reach the phone's files.
- The box has its own pretend disk: the shipped image is read-only, and your changes go to a throwaway layer that "start fresh" deletes.
- No network at all by default (nothing for it to reach). No shared folders, no access to the phone's storage, contacts, camera, microphone or location. The app asks for **no permissions**.
- Memory, disk and CPU are capped, so a fork bomb or a full-disk `dd` only hurts the box, and the app can stop the box at any moment.
- The ways out are kept as few as possible: text in, text out, and nothing else. Copy/paste goes through the screen only, and nothing is ever pasted from the box into the phone's clipboard without the user pressing a button.
- Dangerous commands (`rm -rf /`, `sudo`, `dd`, fork bombs) are a *lesson*: they really run, inside the box, and the box can be reset.

Plan B (fallback): a Termux-style userland (proot) on the phone's CPU. It is faster and lighter, but the programs are then real processes on the phone, held in only by Android's normal app sandbox, so it does **not** meet "nothing runs on your Android". Only consider it if the author accepts that.

Be honest in the app and README: this is a strong box, not a magic one. Emulators can have bugs, so the claim is "built to keep everything inside, with as few doors as possible", never "impossible to escape".

## Things to check before promising anything

- **Speed and battery:** emulating a computer is slower than running natively. A tiny Linux (BusyBox-style) should be fine for lessons and games, but older phones might struggle. Needs a real test, ideally on the author's phone.
- **Size and start time:** the image makes the APK bigger; booting should feel instant (snapshot the booted state if possible).
- **Choice of emulator:** reuse a well-known open-source one (only light, permissively licensed code, checked first) instead of writing one; write the exact pick into the spec.
- **Which tools in the image:** a small set to start (shell, core tools, `nano`/`vi`, `grep`, `less`, `man` pages, a couple of fun programs), matching what beginners will meet.
- **F-Droid rules:** everything must build from open source with no closed parts, which fits repeatable builds like the AppImage work. Check the current rules when the time comes.
- **Google Play rules** (only if ever tried): Android limits running downloaded programs, and Play reviews terminal-like apps. An emulator that keeps its programs as data is the gentler fit, but needs checking then.
- **Antivirus:** the same single-engine "machine-learning" flag worry as with the AppImages applies to APKs. Scan before shipping, same flow.

## Why not a pretend shell

The first idea was a small made-up shell with a handful of commands. It is the safest by far, but it only teaches the commands we write, and the author wants *every* command to work. An emulated Linux gives that. A small pretend shell stays an option for a very old phone or as the lesson mode inside the same app.

## What a day looks like

1. Open the app. It greets you and shows today's tiny lesson ("Today: moving around with `cd`").
2. A few guided steps in the box, with plain-words hints, same friendly tone as the PC app.
3. A small challenge ("find the file named notes and show what is inside").
4. Or pick a game from the `/play` menu.
5. Done: streak goes up, tomorrow's topic is shown.

Typo helper ("did you mean?") and `/clippy`-style help can come later, as on the PC (the not-AI search would need the network, so it would be a separate, clearly marked and off-by-default thing, or skipped).

## Open questions for the author

- OK with an app that is bigger and a little slower because of the emulator, in exchange for "nothing runs on the phone"?
- Which phone(s) will you test on?
- Which tools and first lessons come first?
- Same cartridge format as the PC `/play`, so one game works on both? (Recommended.)

## Order of work (when told to go)

1. Short spec with a safety section (the doors list: what goes in, what comes out, nothing else), for the author to approve.
2. A tiny proof: boot the Linux image in the emulator on a PC, then on the phone, and measure speed.
3. Tests that the box cannot see the phone's files or the network.
4. Rendered mock-up of the screens for the author to approve before any app code.
5. Android app shell with lessons, then games, then test on a real phone with the author.
6. Scan the APK, publish it on GitHub, and keep F-Droid packaging notes for a volunteer or later.
