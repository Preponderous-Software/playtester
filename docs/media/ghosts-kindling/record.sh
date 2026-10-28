#!/bin/bash
# Records the three scripted Kindling sessions behind docs/media/ghosts-kindling.png
# and .gif, on the Strata driver's stepped clock, through pt. The sessions in
# this directory were recorded with Kindling 7ecf1fe built against Strata
# 5b6fcd3 (0.7.0, ABI 1.12), then drawn with:
#
#   pt ghosts docs/media/ghosts-kindling -o docs/media/ghosts-kindling.png --title "Kindling 0.1.2, seed 1881"
#   pt ghosts docs/media/ghosts-kindling --gif docs/media/ghosts-kindling.gif --size 720x405 \
#       --title "Kindling 0.1.2, seed 1881"
cd "$(dirname "$0")/../../.."
S=${S:-/tmp/pt-ghosts}            # where the sessions go; KINDLING=~/kindling built against Strata ABI 1.12+
mkdir -p $S; export PYTHONPATH=src PT_ROOT=$S/ghost-run
pt() { python3 -m playtester "$@" > /dev/null 2>>$S/record.err; }
begin() { export PT_SESSION=$1; pt stop; rm -rf $PT_ROOT/$1; pt start --profile kindling-strata --game-dir ${KINDLING:-$HOME/kindling} --seed 1881 --clock stepped; pt await WORLD 30; pt key F1; }
walk() { for i in $(seq $2); do pt hold "$1" 0.5; done; }
begin s01
pt walkto door 40; walk w 3; pt walkto hearth 40
for i in 1 2 3; do pt hold Down 1; pt hold Up 1.5; pt hold Right 0.4; done
pt walkto window 40; pt walkto debris 40; pt walkto debris 40; pt walkto hearth 40
pt stop
begin s02
pt hold Right 1; walk w 6; pt hold Left 1.5; walk w 4; pt walkto mare 40; pt wait 30
pt walkto wagon 40; pt walkto chopping_block 40; pt hold Left 1; walk w 4
pt stop
begin s03
pt walkto door 40; walk w 3; pt hold Left 1; walk w 8; pt wait 6; walk w 4; pt hold Right 0.6; walk w 6
pt wait 25; pt hold Right 1.2; walk w 4; pt walkto hearth 40
pt stop
echo done
