## What this changes

<!-- A short description of the change and why it is needed. -->

Closes #

## How it was tested

<!-- Commands you ran and what they showed. -->

- [ ] `python -m unittest discover -s tests -t .`
- [ ] `python -m py_compile src/playtester/*.py src/playtester/*/*.py examples/*.py ci/*.py tests/*.py`
- [ ] `PT_ROOT=/tmp/pt-smoke pt smoke --profile demo` (for changes to the agent kit)

## Checklist

- [ ] The code stays Python 3.8 compatible, and the agent kit stays standard-library only
- [ ] Documentation is updated where behaviour changed
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]` for user-facing changes
