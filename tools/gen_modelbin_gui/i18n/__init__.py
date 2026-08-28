"""Looks up user-facing GUI text by key, with fallback to English.

Usage:
    from .i18n import t
    t('shell.log.select_font_first')
    t('shell.log.reference_modelbin_not_found', path=reference)

Adding a language: add a new package under this one (e.g. i18n/es/), matching
the per-module file layout of i18n/en/ (one file per GUI source module, each
exporting a STRINGS dict keyed the same way as the English catalog). Register
it in _CATALOGS below. A key missing from a non-English catalog falls back to
the English string automatically.
"""
from . import en as _en

_CATALOGS: dict[str, dict[str, str]] = {
    'en': _en.STRINGS,
}

_active_locale = 'en'


def set_locale(locale: str) -> None:
    global _active_locale
    if locale not in _CATALOGS:
        raise ValueError(f'No string catalog registered for locale {locale!r}.')
    _active_locale = locale


def get_locale() -> str:
    return _active_locale


def t(key: str, **kwargs) -> str:
    """Return the active locale's string for `key`, formatted with `kwargs`.

    Falls back to the English catalog if the active locale has no entry for
    `key`. Placeholders use str.format() syntax (e.g. "{font_name}"), so a
    translation may reorder them freely.
    """
    template = _CATALOGS[_active_locale].get(key)
    if template is None:
        template = _en.STRINGS.get(key)
    if template is None:
        raise KeyError(f'No string catalog entry for key {key!r}.')
    return template.format(**kwargs) if kwargs else template
