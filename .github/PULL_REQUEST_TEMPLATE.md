---
name: Pull request
about: Submit code or documentation changes
title: ""
labels: []
---

## What does this PR do?

One-paragraph summary.

## Linked issues

Fixes #___ / Relates to #___

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds behavior)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Documentation
- [ ] Refactor (no user-visible change)

## How was it tested?

- [ ] `python -m pytest` passes locally
- [ ] `python -m ruff check src tests` is clean
- [ ] I added new tests for the change
- [ ] I tested the GUI manually (describe below)

Manual GUI run:

```
python -m midimap gui
… steps I took …
```

## Checklist

- [ ] I read [CONTRIBUTING.md](./CONTRIBUTING.md)
- [ ] I added an entry under "Unreleased" in [CHANGELOG.md](./CHANGELOG.md)
- [ ] The change matches the project's license (MIT)
