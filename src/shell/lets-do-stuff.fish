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
