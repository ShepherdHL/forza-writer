"""Procedurally-drawn checkbox/radio indicator glyphs — flat outline when
unset, accent-filled when set — replacing ttk's stock OS-native indicator,
which reads as generic utility-software chrome against everything else in
this design system. The radio "on" state is a thin accent ring with a
small solid center dot (a reticle motif) rather than a fully filled
circle, matching the HUD identity instead of a generic material-design
radio.

Split out from apply.py (rather than folded into it) because
output_accents.py's per-format indicator styling needs these same
primitives — apply.py already needs to call *into* output_accents.py, so
sharing this module avoids the two importing each other.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

_GLYPH_SIZE = 15
_ICON_REFS: dict[tuple[int, str], list] = {}  # keeps each Tk interpreter's PhotoImages alive


def _build_indicator_images(p: dict[str, str], master: tk.Misc | None = None) -> dict[str, "ImageTk.PhotoImage"]:
    s = _GLYPH_SIZE
    inset = 2
    c = s // 2

    def _canvas():
        return Image.new("RGBA", (s, s), (0, 0, 0, 0))

    images: dict[str, Image.Image] = {}

    box = [inset, inset, s - 1 - inset, s - 1 - inset]

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["border"], width=1)
    images["check_off"] = img

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["muted_fg"], width=1)
    images["check_off_hover"] = img

    img = _canvas()
    ImageDraw.Draw(img).rectangle(box, outline=p["disabled_fg"], width=1)
    images["check_off_disabled"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=p["accent"], outline=p["accent"])
    d.line([(inset + 2, c), (c - 1, s - inset - 2), (s - inset - 2, inset + 1)],
           fill=p["select_fg"], width=2, joint="curve")
    images["check_on"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=p["disabled_fg"], outline=p["disabled_fg"])
    d.line([(inset + 2, c), (c - 1, s - inset - 2), (s - inset - 2, inset + 1)],
           fill=p["bg"], width=2, joint="curve")
    images["check_on_disabled"] = img

    ellipse_box = [inset, inset, s - 1 - inset, s - 1 - inset]

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["border"], width=1)
    images["radio_off"] = img

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["muted_fg"], width=1)
    images["radio_off_hover"] = img

    img = _canvas()
    ImageDraw.Draw(img).ellipse(ellipse_box, outline=p["disabled_fg"], width=1)
    images["radio_off_disabled"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.ellipse(ellipse_box, outline=p["accent"], width=1)
    r = 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=p["accent"])
    images["radio_on"] = img

    img = _canvas()
    d = ImageDraw.Draw(img)
    d.ellipse(ellipse_box, outline=p["disabled_fg"], width=1)
    d.ellipse([c - r, c - r, c + r, c + r], fill=p["disabled_fg"])
    images["radio_on_disabled"] = img

    # Explicit master, not Tkinter's ambient "default root" (tkinter._default_root)
    # — that global tracks whichever Tk() was created/destroyed most recently
    # process-wide, which silently diverges from `style`'s own interpreter the
    # moment more than one Tk() root exists across a process's lifetime (e.g. a
    # test suite creating several independent tk.Tk() instances in sequence).
    # An image bound to the wrong interpreter fails at element_create time with
    # `image "pyimageN" doesn't exist` on THIS interpreter, since Tk images are
    # per-interpreter despite the auto-generated name being a process-wide counter.
    return {name: ImageTk.PhotoImage(image, master=master) for name, image in images.items()}


def apply_custom_indicators(style: ttk.Style, p: dict[str, str], master: tk.Misc,
                             palette_key: str) -> None:
    """Register the procedural glyphs as ttk elements and re-layout
    TCheckbutton/TRadiobutton to use them. Best-effort: a failure here
    (an unusual Tk build without image-element support, e.g.) must not
    block the app — it just falls back to ttk's stock indicators.
    `palette_key` namespaces the registered elements so more than one
    palette's indicators can be registered on the same Style without
    colliding — pass the caller's live current-palette key explicitly
    rather than reading a module global, since palette selection state
    lives in gui_theme/__init__.py, not here."""
    try:
        check_element = f"Custom.{palette_key}.Checkbutton.indicator"
        radio_element = f"Custom.{palette_key}.Radiobutton.indicator"
        if check_element not in style.element_names():
            images = _build_indicator_images(p, master=master)
            _ICON_REFS[(id(style.tk), palette_key)] = list(images.values())

            style.element_create(
                check_element, "image", images["check_off"],
                ("disabled", "selected", images["check_on_disabled"]),
                ("disabled", images["check_off_disabled"]),
                ("selected", "active", images["check_on"]),
                ("selected", images["check_on"]),
                ("active", images["check_off_hover"]),
                width=_GLYPH_SIZE, height=_GLYPH_SIZE, sticky="w")
            style.element_create(
                radio_element, "image", images["radio_off"],
                ("disabled", "selected", images["radio_on_disabled"]),
                ("disabled", images["radio_off_disabled"]),
                ("selected", "active", images["radio_on"]),
                ("selected", images["radio_on"]),
                ("active", images["radio_off_hover"]),
                width=_GLYPH_SIZE, height=_GLYPH_SIZE, sticky="w")
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                (check_element, {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])

        style.layout("TRadiobutton", [
            ("Radiobutton.padding", {"sticky": "nswe", "children": [
                (radio_element, {"side": "left", "sticky": ""}),
                ("Radiobutton.focus", {"side": "left", "sticky": "", "children": [
                    ("Radiobutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
    except tk.TclError:
        pass
