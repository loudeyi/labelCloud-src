"""Runtime language switching for labelCloud.

The interface ships with Qt's standard translation machinery:

* every user visible string is wrapped in ``tr()`` (or comes from a ``.ui`` file,
  which ``pyuic5``/``uic`` already wraps),
* ``tools/update_translations.py`` extracts those strings, applies the Chinese
  dictionary in :mod:`labelCloud.i18n.translations_zh_cn` and runs ``lrelease`` to
  build ``labelCloud_<locale>.qm`` next to this module,
* this module installs the matching ``QTranslator`` on the running application.

Installing or removing a translator makes Qt post a ``LanguageChange`` event, so
widgets that implement ``changeEvent`` (see ``view/gui.py``) re-translate
themselves immediately — no restart needed.

Log messages stay English on purpose: they are meant to be greppable and to match
upstream labelCloud's wording.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import QCoreApplication, QLocale, QTranslator

from ..control.config_manager import config

#: ``(setting value, label shown in the Language menu)``
SUPPORTED_LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("system", "Follow System Language"),
    ("en", "English"),
    ("zh_CN", "中文（简体）"),
)

SYSTEM = "system"
ENGLISH = "en"
CHINESE = "zh_CN"

CONFIG_SECTION = "USER_INTERFACE"
CONFIG_OPTION = "language"

_translator: Optional[QTranslator] = None
_application: Optional[QCoreApplication] = None


def translation_file(language: str) -> Path:
    """Path of the compiled ``.qm`` file for a language code."""
    return Path(__file__).resolve().parent.joinpath(f"labelCloud_{language}.qm")


def system_language() -> str:
    """Map the OS locale onto one of the languages we actually ship."""
    name = QLocale.system().name()  # e.g. "zh_CN", "en_US"
    if name.startswith("zh"):
        return CHINESE
    return ENGLISH


def resolve_language(setting: str) -> str:
    """Turn the config value (possibly ``system``) into a concrete language code."""
    if not setting or setting == SYSTEM:
        return system_language()
    for code, _label in SUPPORTED_LANGUAGES:
        if code == setting:
            return code
    logging.warning("Unknown language setting '%s'; following the system.", setting)
    return system_language()


def available_languages() -> List[Tuple[str, str]]:
    """Languages that can be selected, including the ``system`` pseudo entry."""
    return list(SUPPORTED_LANGUAGES)


def current_setting() -> str:
    """The configured value: ``system``, ``en`` or ``zh_CN``."""
    return config.get(CONFIG_SECTION, CONFIG_OPTION, fallback=SYSTEM)


def current_language() -> str:
    """The language actually in use right now (never ``system``)."""
    return resolve_language(current_setting())


def install_language(application: Optional[QCoreApplication] = None) -> str:
    """Install the translator matching the current setting.

    Safe to call more than once: the previous translator is removed first, which
    also triggers the ``LanguageChange`` event that makes the UI re-translate.
    Returns the effective language code.
    """
    global _translator, _application

    app = application or _application or QCoreApplication.instance()
    if app is None:  # nothing to translate yet (e.g. in tests)
        return resolve_language(current_setting())
    _application = app

    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None

    language = resolve_language(current_setting())
    if language != ENGLISH:
        qm_file = translation_file(language)
        if qm_file.is_file():
            # no parent: the module keeps the only reference, so the previous
            # translator is really destroyed when the language changes
            translator = QTranslator()
            if translator.load(str(qm_file)):
                app.installTranslator(translator)
                _translator = translator
            else:
                logging.warning("Failed to load translation file %s.", qm_file)
        else:
            logging.warning(
                "No translation file %s found; interface stays English. "
                "Run tools/update_translations.py to build it.",
                qm_file,
            )
    logging.info("Interface language set to '%s'.", language)
    return language


def set_language(setting: str, application: Optional[QCoreApplication] = None) -> str:
    """Persist a new language setting and apply it immediately."""
    config.set(CONFIG_SECTION, CONFIG_OPTION, setting)
    from ..control.config_manager import config_manager

    config_manager.write_into_file()
    return install_language(application)
