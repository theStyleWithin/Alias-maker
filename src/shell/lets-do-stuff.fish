# Alias Maker's window title for fish: "Let'sdostuff~" instead of "fish ~".
#
# Loaded only inside the Alias Maker window (aliasmaker starts fish with
# --init-command "source <this file>"), after your own fish config, so it only
# changes the title. It's still the same fish: your prompt, settings and commands
# are untouched, and Konsole or any other terminal is unaffected.
#
# The name comes from $ALIASMAKER_NAME (set by aliasmaker), so it can change later.

function fish_title
    set -l name "Let'sdostuff"
    if set -q ALIASMAKER_NAME; and test -n "$ALIASMAKER_NAME"
        set name $ALIASMAKER_NAME
    end

    # Where you are, written the usual way: ~ for your home folder, ~/Games below it.
    set -l home_pattern '^'(string escape --style=regex -- $HOME)'(?=/|$)'
    set -l where (string replace -r -- $home_pattern '~' $PWD)

    # While a program runs, add its name, like fish normally does.
    set -l running (string split -f1 ' ' -- "$argv[1]")
    if test -n "$running"
        echo "$name$where : $running"
    else
        echo "$name$where"
    end
end
