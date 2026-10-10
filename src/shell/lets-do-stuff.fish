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
# system info (fastfetch) still next to it.
#
# It also adds the /clippy slash command: "/clippy chrooting" looks chrooting up
# (CachyOS wiki, Arch Wiki, manual pages on this PC) and never runs chroot.

# The welcome when a terminal opens: a big DOIT where the CachyOS logo would be. Your
# system info from fastfetch still shows next to it; without fastfetch, just DOIT.
set -g __aliasmaker_logo (status dirname)/doit-logo.txt

function fish_greeting
    if type -q fastfetch; and test -f $__aliasmaker_logo
        fastfetch --logo $__aliasmaker_logo --logo-type file --logo-color-1 96
    else if test -f $__aliasmaker_logo
        set_color --bold brcyan
        string replace -a '$1' '' <$__aliasmaker_logo
        set_color normal
    end
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

# /clippy <topic>: fish doesn't know any command starting with "/", so it calls
# fish_command_not_found. Catch /clippy there and hand it to Alias Maker; anything
# else goes to whatever handler you already had (CachyOS's, or fish's own).
if functions -q fish_command_not_found; and not functions -q __aliasmaker_previous_command_not_found
    functions --copy fish_command_not_found __aliasmaker_previous_command_not_found
end

function fish_command_not_found
    if test "$argv[1]" = /clippy
        doit clippy $argv[2..-1]
        return
    end
    if functions -q __aliasmaker_previous_command_not_found
        __aliasmaker_previous_command_not_found $argv
    else
        printf "fish: Unknown command: %s\n" $argv[1] >&2
    end
end
