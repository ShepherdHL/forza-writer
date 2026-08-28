"""Curated per-script "alphabet" character sets for the Generator tab's
Characters section: real generation support for scripts beyond Latin,
completing what the script sub-tabs (`forza_writer/script_detect.py`)
deliberately deferred when they were added ("filtering/browsing only for
now: Characters below still uses the ASCII sets regardless of script").

Scope, per the decision this was built against: the tool places one
flat, unshaped glyph per character, with no ligatures, no contextual
letterforms, no positioning combining marks relative to a base
character. That works cleanly for scripts built from fixed independent
letterforms (Cyrillic, Greek: literally the same uppercase/lowercase
model Latin already uses), and is offered here on a best-effort basis
for scripts that don't fully fit that model, with the mismatch called
out explicitly rather than silently:

- Arabic normally connects each letter to its neighbors; this offers
  isolated letterforms only (`SHAPING_CAVEATS`).
- Devanagari/Thai vowel signs and Thai tone marks normally stack
  above/below/around a consonant; here they're flat standalone glyphs.
- Korean is offered as individual Jamo (the 19 consonants + 21 vowels;
  Korean genuinely is alphabetic at that level), not composed syllable
  blocks, since composing e.g. ㅎ+ㅏ+ㄴ into 한 needs real text shaping
  this tool doesn't have.
- Japanese Hiragana/Katakana are complete standard syllabary tables
  (46 base + dakuten/handakuten + small kana); these render correctly
  with the flat model since kana characters don't combine positionally.

Simplified/Traditional Chinese have no small fixed alphabet the same way
an alphabetic script does (thousands of Hanzi); intentionally absent
from `ALPHABETS`; `NO_ALPHABET_SCRIPTS` flags this so the GUI can point
at "All characters in font" (already supported) instead of pretending a
curated checkbox list exists.

Each script maps to an ordered list of (group_label, characters) pairs:
mirrors the existing Latin Characters section's Uppercase/Lowercase
split, just per-script instead of hardcoded to `string.ascii_*`.
"""

from __future__ import annotations

ALPHABETS: dict[str, list[tuple[str, str]]] = {
    "Cyrillic": [
        ("Uppercase", "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"),
        ("Lowercase", "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"),
    ],
    "Greek": [
        ("Uppercase", "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"),
        ("Lowercase", "αβγδεζηθικλμνξοπρστυφχψω" + "ς"),  # trailing: word-final sigma
    ],
    "Japanese": [
        ("Hiragana",
         "あいうえおかきくけこさしすせそたちつてとなにぬねの"
         "はひふへほまみむめもやゆよらりるれろわをん"
         "がぎぐげござじずぜぞだぢづでどばびぶべぼ"
         "ぱぴぷぺぽっゃゅょ"),
        ("Katakana",
         "アイウエオカキクケコサシスセソタチツテトナニヌネノ"
         "ハヒフヘホマミムメモヤユヨラリルレロワヲン"
         "ガギグゲゴザジズゼゾダヂヅデドバビブベボ"
         "パピプペポッャュョー"),
    ],
    "Korean": [
        ("Consonants", "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"),
        ("Vowels", "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"),
    ],
    "Devanagari": [
        ("Vowels", "अआइईउऊऋएऐओऔ"),
        ("Consonants", "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह"),
    ],
    "Thai": [
        ("Consonants", "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ"),
        ("Vowels", "ะัาำิีึืุูเแโใไ"),
        ("Tone marks", "่้๊๋"),
    ],
    "Arabic": [
        ("Letters", "ابتثجحخدذرزسشصضطظعغفقكلمنهوي" + "ءأإؤئآةى"),
    ],
    "Hebrew": [
        # 22 base letters plus the 5 final (sofit) forms used at the end of
        # a word; unlike Arabic's positional shaping, these are already
        # distinct standalone codepoints (HEBREW LETTER FINAL KAF, etc.),
        # so this fits the flat one-glyph-per-character model with no
        # shaping caveat needed, unlike the niqqud group below.
        ("Letters", "אבגדהוזחטיכלמנסעפצקרשת" + "ךםןףץ"),
        # Vowel points (niqqud): combining marks normally stacked above/
        # below a base letter; here they render as flat standalone glyphs,
        # same caveat as Devanagari/Thai (see SHAPING_CAVEATS below).
        ("Niqqud (vowel points)", "ְֱֲֳִֵֶַָֹֻּֽׁׂ"),
    ],
}

# Scripts with no small fixed alphabet: not in ALPHABETS above; the
# Generator tab shows a hint instead of checkboxes for these.
NO_ALPHABET_SCRIPTS = {"Simplified Chinese", "Traditional Chinese"}

# Chinese does not have an alphabet-sized complete set. These deliberately
# small, transparent sets are for validating a generator/font or building a
# tightly scoped pack. Real text should normally be pasted into the Generator's
# "Extra characters" field; full Han coverage remains an explicit advanced
# action in the GUI rather than being hidden behind "Symbols".
CHINESE_STRUCTURAL_TEST = (
    "一二三十人口日月田目山川大小上下左右中木本末未水火土金雨竹米石"
    "女女子好心手足口耳目力刀工王玉白百千天文方圆東西南北春夏秋冬"
    "明林森休体品晶众从坐家安空国車馬魚鳥龍門問間語書學愛新長高"
)
CHINESE_PUNCTUATION = "，。！？；：、（）《》〈〉「」『』【】…—"
CHINESE_VARIANTS: dict[str, str] = {
    "Simplified Chinese": "门问间语书学爱车马鱼鸟龙国东体长圆众",
    "Traditional Chinese": "門問間語書學愛車馬魚鳥龍國東體長圓眾",
}

# One-click sample text per script, for checking how a font actually renders
# before committing to a full generation run.
#
# Each script maps to an ordered list of (label, text) options rather than a
# single string: a script can offer several different samples (e.g. Hebrew's
# alphabet row, a real scripture passage, and a deliberately-fictional one)
# and the GUI lets the user pick/cycle between them. `PANGRAM_SCRIPTS` still
# governs script order; within a script, option order is display order.
#
# Most entries are pangrams (or the nearest equivalent a script has): short
# passages chosen to exercise as much of a script's repertoire as possible, so
# a single click reveals missing glyphs, bad spacing, or a font that only
# covers ASCII. That makes them a *rendering* test, deliberately not the same
# thing as ALPHABETS above: those are exhaustive character sets used to
# decide what to generate; these are natural text used to decide whether a
# font is worth generating from. A verse or narrative passage, by contrast,
# is natural language, not engineered for coverage; it won't reliably touch
# every glyph in the way a real pangram does (verified, e.g., against Hebrew:
# none of the well-known "curious fish" Hebrew pangram variants actually
# cover all 5 final letter forms), so treat non-pangram entries as a "does
# this look right" preview, not a coverage guarantee.
#
# The Japanese entry is the Iroha, a classical poem that famously uses each
# kana exactly once. The Latin, Korean, Cyrillic, Greek, Thai and Arabic
# entries are the conventional pangrams for their scripts.
#
# Chinese has no pangram: the writing system has no small closed repertoire
# to exhaust, so both variants reuse CHINESE_STRUCTURAL_TEST above, which
# exists for exactly this "is this font usable" purpose.
#
# Devanagari is deliberately absent rather than guessed at: a sample nobody
# has verified is worse than no button, and the UI simply omits the option for
# scripts with no entry (see PANGRAM_SCRIPTS).
PANGRAMS: dict[str, list[tuple[str, str]]] = {
    "Latin": [
        # "JUMPS", not "JUMPED": the past tense drops the only S in the
        # sentence, which quietly stops it being a pangram at all (caught by
        # test_latin_sample_covers_the_whole_alphabet_and_all_ten_digits).
        ("Pangram", "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG. 1234567890"),
    ],
    "Japanese": [
        ("Iroha (pangram)", (
            "いろはにほへと ちりぬるを わかよたれそ つねならむ "
            "うゐのおくやま けふこえて あさきゆめみし ゑひもせす"
        )),
    ],
    "Korean": [("Pangram", "키스의 고유조건은 입술끼리 만나야 하고 특별한 기술은 필요치 않다.")],
    "Cyrillic": [("Pangram", "Съешь же ещё этих мягких французских булок, да выпей чаю.")],
    "Greek": [("Pangram", "διαφυλάξτε γενικά τη ζωή σας από βαθειά ψυχικά τραύματα.")],
    "Thai": [
        ("Pangram", (
            "นายสังฆภัณฑ์ เฮงพิทักษ์ฝั่ง ผู้เฒ่าซึ่งมีอาชีพเป็นฅนขายฃวด "
            "ถูกตำรวจปฏิบัติการจับฟ้องศาล ฐานลักนาฬิกาคุณหญิงฉัตรชฎา ฌานสมาธิ"
        )),
    ],
    "Arabic": [("Pangram", "أبجد هوز حطي كلمن سعفص قرشت ثخذ ضظغ")],
    "Hebrew": [
        # Not a pangram: a plain row of the alphabet (base letters + the 5
        # final forms), reusing ALPHABETS["Hebrew"] directly so it can't
        # drift out of sync with the actual letter list.
        ("Alphabet", ALPHABETS["Hebrew"][0][1]),
        # A real scripture passage (John 19:19-22, the "INRI" inscription
        # passage) in Franz Delitzsch's Hebrew New Testament (1877/1892,
        # public domain), the standard Hebrew NT translation. Note this is
        # a *translation*: the New Testament itself was composed in Greek,
        # not Hebrew, so there is no "original Hebrew" of John to draw from.
        # Sourced from stepbible.org's Delitzsch text; verified here only as
        # well-formed Hebrew script (every character falls in the Hebrew
        # Unicode block), not independently checked against a scan for
        # translation accuracy; worth a spot-check before relying on it.
        ("John 19:19-22 (Delitzsch Hebrew NT)", (
            "וּפִילָטוֹס כָּתַב עַל־לוּחַ וַיָּשֶׂם עַל־הַצְּלָב וְזֶה דְבַר־הַכָּתוּב יֵשׁוּעַ הַנָּצְרִי "
            "וִיהוּדִים רַבִּים קָרְאוּ אֶת־הַכָּתוּב הַזֶּה כִּי הַמָּקוֹם אֲשֶׁר נִצְלַב־שָׁם יֵשׁוּעַ הָיָה "
            "וַיֹּאמְרוּ רָאשֵׁי כֹּהֲנֵי הַיְּהוּדִים אֶל־פִּילָטוֹס אַל־נָא תִכְתֹּב מֶלֶךְ הַיְּהוּדִים "
            "וַיַּעַן פִּילָטוֹס וַיֹּאמַר אֵת־אֲשֶׁר־כָּתַבְתִּי כָּתָבְתִּי׃"
        )),
        # Not scripture: an original fictional/joke passage (a parody verse
        # numbered "Revelation 1:19½", written by a Forza Writer contributor)
        # translated into Hebrew. Machine-translated, unverified by a native
        # speaker; flagged as a joke in its own label so nobody mistakes it
        # for a real Bible passage.
        ("Joke: Revelation 1:19½ (not real scripture)", (
            "וַיֹּאמֶר אֵלַי: \"צְפֵה בַּזְוָעוֹת.\" "
            "וָאֵרֶא וְהִנֵּה הָרְאוּ אוֹתִי דְּבָרִים נוֹרָאִים וְזָרִים אֲשֶׁר לֹא רָאִיתִי מִלְּפָנִים "
            "וְלֹא יָכֹלְתִּי לִסְפֹּר אוֹתָם. "
            "וַיְהִי קוֹל גָּדוֹל כְּקוֹל מַרְכָּבוֹת רַבּוֹת יֹצְאוֹת לַמִּלְחָמָה "
            "וַתְּהִי אֵשׁ וְעָשָׁן וּרְעִידַת הָאָרֶץ. "
            "וָאֹמַר אֵלָיו: \"כֵּן, אֲדֹנִי, אֵלֶּה הֵם זְוָעוֹת בֶּאֱמֶת.\" "
            "וַיֹּאמֶר אֵלַי: \"עַל־כֵּן כְּתֹב אֶת אֲשֶׁר רָאִיתָ.\""
        )),
    ],
    "Simplified Chinese": [("Structural test set", CHINESE_STRUCTURAL_TEST)],
    "Traditional Chinese": [("Structural test set", CHINESE_STRUCTURAL_TEST)],
}

# Scripts that actually have sample text, in canonical SCRIPTS order: the
# GUI iterates this rather than PANGRAMS directly so the buttons appear in the
# same order as the script tabs instead of dict-insertion order.
PANGRAM_SCRIPTS: list[str] = [
    "Latin", "Cyrillic", "Greek", "Japanese", "Korean",
    "Traditional Chinese", "Simplified Chinese", "Arabic", "Hebrew", "Thai",
]


def pangrams_for(script: str) -> list[tuple[str, str]]:
    """Every (label, text) sample option for `script`, in display order;
    empty list if there isn't a verified one. Prefer this over pangram_for()
    for anything that should let the user pick/cycle between options."""
    return PANGRAMS.get(script, [])


def pangram_for(script: str) -> str | None:
    """The first/default sample text for `script`, or None if there isn't a
    verified one. Back-compat single-string wrapper around pangrams_for();
    prefer pangrams_for() for the full list of options."""
    options = PANGRAMS.get(script)
    return options[0][1] if options else None


def groups_for_script(script: str) -> list[tuple[str, str]]:
    """Curated, bounded character groups displayed for *script*.

    Chinese groups are test/scoping aids rather than a claimed alphabet.
    """
    if script in CHINESE_VARIANTS:
        return [
            ("Structural test set", CHINESE_STRUCTURAL_TEST),
            ("Chinese punctuation", CHINESE_PUNCTUATION),
            ("Script variants", CHINESE_VARIANTS[script]),
        ]
    return ALPHABETS.get(script, [])

# Shown as a caveat under the checkboxes for scripts where this tool's
# flat one-glyph-per-character model produces something short of normal
# typeset/handwritten text for that language; see the module docstring.
SHAPING_CAVEATS: dict[str, str] = {
    "Korean": ("Generates individual Jamo (consonant/vowel letters), not composed "
               "syllable blocks; one flat shape per character means 한 "
               "comes out as ㅎㅏㄴ, not the combined block."),
    "Arabic": ("Each letter renders in its isolated form: Arabic normally "
               "connects letters to their neighbors, which this tool doesn't do."),
    "Devanagari": ("Independent letters only: vowel signs are placed as flat "
                    "standalone marks, not stacked onto a consonant the way real "
                    "Devanagari text combines them."),
    "Thai": ("Vowel signs and tone marks are placed as flat standalone glyphs, not "
             "positioned above/below/around a consonant the way real Thai text does."),
    "Hebrew": ("Niqqud (vowel points) are placed as flat standalone marks, not "
               "stacked above/below a letter the way real pointed Hebrew text does. "
               "The base letters (including final forms) are unaffected by this: "
               "those are already distinct standalone characters, not combined."),
}


def chars_for_script(script: str) -> set[str]:
    """Every character across every group for a script, or an empty set
    if the script has no curated alphabet (see NO_ALPHABET_SCRIPTS)."""
    chars: set[str] = set()
    for _label, letters in ALPHABETS.get(script, []):
        chars.update(letters)
    return chars
