# Security Policy

## Supported versions

Playtester has no stable releases yet. Security fixes go to the `main` branch;
install from `main` (or the newest tag) to get them.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Report it privately through GitHub's private vulnerability reporting:
open the repository's **Security** tab and choose **Report a vulnerability**
(or go straight to
[the advisory form](https://github.com/Preponderous-Software/playtester/security/advisories/new)).
Include what you found, how to reproduce it, and what an attacker could do
with it.

You can expect an acknowledgement within a week. Fixes are made in a private
fork where needed, released, and then disclosed in a GitHub security
advisory that credits the reporter unless they prefer otherwise.

## Scope

Playtester starts games, Xvfb servers and other processes on the machine it
runs on, and sends them input. Things worth reporting include:

- a way for `pt` to signal, stop or send input to a process it did not start;
- a profile, report or probe file that makes `pt` or the aggregator run
  unintended commands or write outside the session or run directory;
- the coordinator skill or agent prompt leading an agent to act outside the
  game under test.

Profiles are trusted input: a profile's `build` and `launch` commands run as
given, so only use profiles you have read.
