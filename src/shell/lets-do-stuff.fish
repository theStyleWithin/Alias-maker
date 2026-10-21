# Alias Maker's fish setup: the terminal says "Let'sdostuff~" instead of "fish ~".
#
# To someone new to Linux, "fish ~" means nothing. Inside the Alias Maker window,
# both the window title and the prompt line say Let'sdostuff, followed by the folder
# you're in (~ is your home folder):
#
#   title:   Let'sdostuff~            (Let'sdostuff~ : htop while a program runs)
#   prompt:  Let'sdostuff~ ❯          (Let'sdostuff~/Games ❯ in another folder)
#
# Loaded only inside the Alias Maker window (aliasmaker starts fish with
# --init-command "source <this file>"), after your own fish config. It's still the
# same fish: your settings, functions and commands are untouched, and Konsole or
# any other terminal is unaffected.
#
# The name comes from $ALIASMAKER_NAME (set by aliasmaker), so it can change later.
#
# When a terminal opens, it shows a big DOIT instead of the CachyOS logo, with your
# PC's info next to it.
#
# It also adds the /clippy slash command: "/clippy chrooting" looks chrooting up
# (CachyOS wiki, Arch Wiki, manual pages on this PC) and never runs chroot.
#
# And commands you make in Alias Maker work right away in this window: no need to
# open a new one.

# The welcome when a terminal opens: a big DOIT with this PC's info next to it (from
# fastfetch when it's installed, or Alias Maker's own when it isn't).
set -g __aliasmaker_doit (status dirname)/../doit
# From the AppImage, a doit that brings its own Python (the PC may have none)
if set -q ALIASMAKER_DOIT_DIR; and test -x $ALIASMAKER_DOIT_DIR/doit
    set -g __aliasmaker_doit $ALIASMAKER_DOIT_DIR/doit
end

# doit works here even if Alias Maker was never installed onto your PATH.
if not command -q doit; and not functions -q doit
    function doit --description "Alias Maker"
        $__aliasmaker_doit $argv
    end
end

function fish_greeting
    $__aliasmaker_doit --welcome
end

function __aliasmaker_name
    if set -q ALIASMAKER_NAME; and test -n "$ALIASMAKER_NAME"
        echo $ALIASMAKER_NAME
    else
        echo "Let'sdostuff"
    end
end

# Where you are, written the usual way: ~ for your home folder, ~/Games below it.
function __aliasmaker_where
    set -l home_pattern '^'(string escape --style=regex -- $HOME)'(?=/|$)'
    string replace -r -- $home_pattern '~' $PWD
end

function fish_title
    set -l name (__aliasmaker_name)
    set -l where (__aliasmaker_where)
    # While a program runs, add its name, like fish normally does.
    set -l running (string split -f1 ' ' -- "$argv[1]")
    if test -n "$running"
        echo "$name$where : $running"
    else
        echo "$name$where"
    end
end

function fish_prompt
    set -l last_status $status
    set_color --bold brcyan
    echo -n (__aliasmaker_name)(__aliasmaker_where)
    set_color normal
    # The arrow turns red when the last command failed, so you can tell at a glance.
    if test $last_status -eq 0
        set_color --bold brmagenta
    else
        set_color --bold red
    end
    echo -n ' ❯ '
    set_color normal
end

# Your own one-word commands live in ~/.config/fish/conf.d/alias-maker.fish, which
# fish reads when a terminal opens. Alias Maker rewrites that file whenever you create,
# edit or delete a command, so check it before each prompt and reload it when it
# changed. Returns 0 when it reloaded.
function __aliasmaker_shortcuts_file
    echo $__fish_config_dir/conf.d/alias-maker.fish
end

function __aliasmaker_reload_shortcuts
    set -l file (__aliasmaker_shortcuts_file)
    set -l text ""
    if test -f $file
        set text (string collect < $file)
    end
    if test "$text" = "$__aliasmaker_shortcuts_text"
        return 1
    end
    set -g __aliasmaker_shortcuts_text $text
    # Remove the old ones first, so a deleted or renamed command really goes away.
    for name in $__aliasmaker_shortcut_names
        functions --erase -- $name
    end
    set -e __aliasmaker_shortcut_names
    if test -f $file
        source $file
    end
    return 0
end

function __aliasmaker_check_shortcuts --on-event fish_prompt
    __aliasmaker_reload_shortcuts
end

# Fish already read the file when this window opened; remember it as it is now.
if test -f (__aliasmaker_shortcuts_file)
    set -g __aliasmaker_shortcuts_text (string collect < (__aliasmaker_shortcuts_file))
else
    set -g __aliasmaker_shortcuts_text ""
end

# /clippy <topic>: typing /clippy turns into "doit clippy" as soon as you press space
# or Enter (a fish abbreviation), so it's never shown in red as an unknown command.
abbr --add __aliasmaker_clippy --position command --regex '^/clippy$' -- 'doit clippy' 2>/dev/null
abbr --add __aliasmaker_ai --position command --regex '^/ai$' -- 'doit ai' 2>/dev/null
abbr --add __aliasmaker_swapai --position command --regex '^/swapai$' -- 'doit swapai' 2>/dev/null

# Backup for older fish without that kind of abbreviation: fish doesn't know any command
# starting with "/", so it calls fish_command_not_found. Catch /clippy there and hand
# it to Alias Maker. The same spot catches a command you made a moment ago in the
# Alias Maker window while this prompt was already waiting. Anything else goes to
# whatever handler you already had (CachyOS's, or fish's own).
if functions -q fish_command_not_found; and not functions -q __aliasmaker_previous_command_not_found
    functions --copy fish_command_not_found __aliasmaker_previous_command_not_found
end

function fish_command_not_found
    if test "$argv[1]" = /clippy
        doit clippy $argv[2..-1]
        return
    end
    if test "$argv[1]" = /ai
        doit ai $argv[2..-1]
        return
    end
    if test "$argv[1]" = /swapai
        doit swapai $argv[2..-1]
        return
    end
    if __aliasmaker_reload_shortcuts; and functions -q -- $argv[1]
        $argv
        return
    end
    # Explain in plain words: one of your own phrases typed without doit, a typo, or
    # software that isn't installed. Stops here if it was one of your phrases.
    doit --not-found $argv >&2; and return 127
    # The handler that was there before often says which package has the program (pkgfile
    # on Arch, command-not-found on Ubuntu). Skip fish's plain default: it would only repeat.
    if functions -q __aliasmaker_previous_command_not_found
        and not functions __aliasmaker_previous_command_not_found | string match -q '*__fish_default_command_not_found_handler*'
        __aliasmaker_previous_command_not_found $argv
    end
end
