# United States plate templates

`us-ca-passenger-current.json` is the only template built so far (one of
the five proof-of-concept templates -- see
`docs/PLATE_GENERATOR_ARCHITECTURE.md`). This directory is the reserved
location for the other 49 states' plates as they get built; nothing else is
here yet.

## Naming convention

`us-<state>-<plate_type>-<era>.json`, where `<state>` is the state's own
lowercase two-letter postal abbreviation:

```
us-al-passenger-current.json     Alabama
us-ak-passenger-current.json     Alaska
us-az-passenger-current.json     Arizona
...
us-ca-passenger-current.json     California  (built)
...
us-wy-passenger-current.json     Wyoming
```

A state with more than one standard (motorcycle, commercial, a historical
variant) gets one file per standard, same as `us-ca-passenger-current.json`
would if a `us-ca-motorcycle-current.json` were added alongside it --
`plate_type`/`era` in the filename, not a separate directory.

## Adding one

Follow `docs/PLATE_TEMPLATE_SCHEMA.md`'s "How to add a new jurisdiction"
section. Nothing about the loader or renderer needs to change -- dropping a
correctly-formed `<template_id>.json` file into this directory is
sufficient; `forza_writer/plates/loader.py`'s registry scan picks it up
automatically (see that module's docstring for the directory-nesting
convention this whole `data/plate_templates/` tree follows).
