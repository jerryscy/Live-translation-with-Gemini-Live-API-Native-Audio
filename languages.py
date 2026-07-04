"""Chirp 3: HD supported languages (GA + Preview).

Compiled from the official GCP documentation:
    https://cloud.google.com/text-to-speech/docs/chirp3-hd#language_availability

Each entry is (display_name, bcp47_code, is_preview). At the time of writing
only Punjabi (India) and Chinese (Hong Kong) are in Preview; everything else
is GA. The list is exposed to the frontend so the input/output language
dropdowns stay in sync with a single source of truth.
"""

from typing import List, Dict

# (Display name, BCP-47 code, is_preview)
CHIRP3_HD_LANGUAGES = [
    ("Arabic (Generic)", "ar-XA", False),
    ("Bengali (India)", "bn-IN", False),
    ("Bulgarian (Bulgaria)", "bg-BG", False),
    ("Chinese (Hong Kong)", "yue-HK", True),   # Preview
    ("Croatian (Croatia)", "hr-HR", False),
    ("Czech (Czech Republic)", "cs-CZ", False),
    ("Danish (Denmark)", "da-DK", False),
    ("Dutch (Belgium)", "nl-BE", False),
    ("Dutch (Netherlands)", "nl-NL", False),
    ("English (Australia)", "en-AU", False),
    ("English (India)", "en-IN", False),
    ("English (United Kingdom)", "en-GB", False),
    ("English (United States)", "en-US", False),
    ("Estonian (Estonia)", "et-EE", False),
    ("Finnish (Finland)", "fi-FI", False),
    ("French (Canada)", "fr-CA", False),
    ("French (France)", "fr-FR", False),
    ("German (Germany)", "de-DE", False),
    ("Greek (Greece)", "el-GR", False),
    ("Gujarati (India)", "gu-IN", False),
    ("Hebrew (Israel)", "he-IL", False),
    ("Hindi (India)", "hi-IN", False),
    ("Hungarian (Hungary)", "hu-HU", False),
    ("Indonesian (Indonesia)", "id-ID", False),
    ("Italian (Italy)", "it-IT", False),
    ("Japanese (Japan)", "ja-JP", False),
    ("Kannada (India)", "kn-IN", False),
    ("Korean (South Korea)", "ko-KR", False),
    ("Latvian (Latvia)", "lv-LV", False),
    ("Lithuanian (Lithuania)", "lt-LT", False),
    ("Malayalam (India)", "ml-IN", False),
    ("Mandarin Chinese (China)", "cmn-CN", False),
    ("Marathi (India)", "mr-IN", False),
    ("Norwegian Bokm\u00e5l (Norway)", "nb-NO", False),
    ("Polish (Poland)", "pl-PL", False),
    ("Portuguese (Brazil)", "pt-BR", False),
    ("Punjabi (India)", "pa-IN", True),        # Preview
    ("Romanian (Romania)", "ro-RO", False),
    ("Russian (Russia)", "ru-RU", False),
    ("Serbian (Cyrillic)", "sr-RS", False),
    ("Slovak (Slovakia)", "sk-SK", False),
    ("Slovenian (Slovenia)", "sl-SI", False),
    ("Spanish (Spain)", "es-ES", False),
    ("Spanish (United States)", "es-US", False),
    ("Swahili (Kenya)", "sw-KE", False),
    ("Swedish (Sweden)", "sv-SE", False),
    ("Tamil (India)", "ta-IN", False),
    ("Telugu (India)", "te-IN", False),
    ("Thai (Thailand)", "th-TH", False),
    ("Turkish (Turkey)", "tr-TR", False),
    ("Ukrainian (Ukraine)", "uk-UA", False),
    ("Urdu (India)", "ur-IN", False),
    ("Vietnamese (Vietnam)", "vi-VN", False),
]


def languages_json() -> List[Dict[str, object]]:
    """Return the language list as JSON-serialisable dicts for the frontend."""
    return [
        {"name": name, "code": code, "preview": preview}
        for (name, code, preview) in CHIRP3_HD_LANGUAGES
    ]


def name_for_code(code: str) -> str:
    """Look up the display name for a BCP-47 code (falls back to the code)."""
    for name, c, _ in CHIRP3_HD_LANGUAGES:
        if c == code:
            return name
    return code
