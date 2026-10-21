# Alias Maker's setup for bash. The Alias Maker window starts your own bash with this file
# (bash --rcfile), so it only touches Alias Maker windows: every other terminal stays as it
# was. It's still your bash underneath: your .bashrc, aliases, functions, history and syntax
# all work as usual. Only the look changes: the prompt and title say Let'sdostuff~ (set
# ALIASMAKER_KEEP_PROMPT=1 to keep your own prompt), plus the Alias Maker extras below.

# ---- 1. your own bash setup, loaded the way a normal terminal loads it ----
[ -r /etc/bash.bashrc ] && . /etc/bash.bashrc
[ -r "$HOME/.bashrc" ] && . "$HOME/.bashrc"

# ---- 2. Alias Maker's parts ----
[ -n "${__aliasmaker_ready-}" ] && return 0
__aliasmaker_ready=1
__aliasmaker_name="${ALIASMAKER_NAME-}"
[ -n "$__aliasmaker_name" ] || __aliasmaker_name="Let'sdostuff"
__aliasmaker_shortcuts="${XDG_CONFIG_HOME:-$HOME/.config}/alias-maker/shortcuts.bash"
__aliasmaker_mark=$'\e[35;1m'

# Your one-word commands (made in the window or with doit create)
[ -r "$__aliasmaker_shortcuts" ] && . "$__aliasmaker_shortcuts"

# The prompt and the window title: Let'sdostuff~ in your home folder, Let'sdostuff~/Games below it.
# \w is the folder (~ for home); it's never run through the shell, so odd folder names are safe.
__aliasmaker_before() {  # first: keep the exit status of your last command (the arrow turns red)
    if [ "$?" -eq 0 ]; then __aliasmaker_mark=$'\e[35;1m'; else __aliasmaker_mark=$'\e[31;1m'; fi
}
__aliasmaker_after() {   # last: after your own prompt setup has had its say
    local here
    if [[ "$PWD" == "$HOME" || "$PWD" == "$HOME"/* ]]; then here="~${PWD#"$HOME"}"; else here="$PWD"; fi
    printf '\e]0;%s\a' "${__aliasmaker_name}${here//[[:cntrl:]]/}"
    [ -n "${ALIASMAKER_KEEP_PROMPT-}" ] && return 0
    PS1="\\[\\e[96;1m\\]${__aliasmaker_name}\\w\\[\\e[0m\\] \\[\${__aliasmaker_mark}\\]❯\\[\\e[0m\\] "
}
if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
    PROMPT_COMMAND=(__aliasmaker_before "${PROMPT_COMMAND[@]}" __aliasmaker_after)
else
    __aliasmaker_existing="${PROMPT_COMMAND-}"
    while [[ "$__aliasmaker_existing" == *[\;[:space:]] ]]; do __aliasmaker_existing="${__aliasmaker_existing%?}"; done
    PROMPT_COMMAND="__aliasmaker_before${__aliasmaker_existing:+; $__aliasmaker_existing}; __aliasmaker_after"
    unset __aliasmaker_existing
fi

# /clippy <topic>: when you press Enter, /clippy turns into "doit clippy" (bash can't have a
# command called /clippy). It looks a topic up and never runs it. This only touches Enter when
# Enter does the ordinary thing (accept the line), so it never fights your own key settings.
__aliasmaker_clippy() {
    if [[ "$READLINE_LINE" == "/clippy" || "$READLINE_LINE" == "/clippy "* ]]; then
        READLINE_LINE="doit clippy${READLINE_LINE#/clippy}"
        READLINE_POINT=${#READLINE_LINE}
    fi
}
if [[ "$(bind -P 2>/dev/null)" == *'accept-line can be found on'*'"\C-m"'* ]]; then
    bind -x '"\C-x\C-a": __aliasmaker_clippy' 2>/dev/null
    bind '"\C-m": "\C-x\C-a\C-j"' 2>/dev/null
fi

# A command bash doesn't know: say why in plain words (a typo, software that isn't installed,
# or one of your own phrases typed without doit), then let the handler you already had add
# its hint (Ubuntu's names the package). Also catches a command made a moment ago in the
# window while this prompt was already waiting.
if declare -F command_not_found_handle >/dev/null; then
    eval "__aliasmaker_previous_not_found() $(declare -f command_not_found_handle | tail -n +2)"
fi
command_not_found_handle() {
    if [ -r "$__aliasmaker_shortcuts" ]; then
        . "$__aliasmaker_shortcuts"
        if declare -F -- "$1" >/dev/null; then "$@"; return $?; fi
    fi
    doit --not-found "$@" >&2 && return 127
    if declare -F __aliasmaker_previous_not_found >/dev/null; then __aliasmaker_previous_not_found "$@"; fi
    return 127
}
