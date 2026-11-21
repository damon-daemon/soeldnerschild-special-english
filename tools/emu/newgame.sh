#!/bin/bash
# newgame.sh [out.png] : cold boot the English build (CUE= for another image), start a new game with the
# defaults (name Ein, infantry, fast messages) and stop at the first scene (block 005 @0, Steindorf). ~60 s
D=$(cd "$(dirname "$0")" && pwd)
WAIT=15 "$D/restart.sh" >/dev/null 2>&1
"$D/hpress.sh" /dev/null Return w w Return w w Return w w w        # skip the logos and movie, title
"$D/hpress.sh" /dev/null E w Return w w w                           # press start
"$D/hpress.sh" /dev/null E w Down w X w w w w w                     # new game -> name entry
"$D/hpress.sh" /dev/null E w Return w X w w w w                     # end name entry, confirm
"$D/hpress.sh" /dev/null E w X w w w w w w                          # yes; troop type: infantry
"$D/hpress.sh" /dev/null E w X w w w w                              # message speed: fast
"$D/hpress.sh" /dev/null E w X w w w w w w w w                      # settings OK
"$D/hpress.sh" /dev/null E w X w w w w w w w w w w w w w w
[ -n "$1" ] && "$D/hshot.sh" "$1"
