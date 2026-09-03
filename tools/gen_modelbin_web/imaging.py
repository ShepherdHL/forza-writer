"""Shared image-to-frontend encoding for the web GUI's handlers.

Every handler that pushes a PIL-rendered preview to the page (Glyph
Inspector, Glyph Template) needs the same PNG-to-data-URI encoding; this is
the one place it lives, rather than each handler module carrying its own
private copy.
"""

from __future__ import annotations

import base64
import io


def image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
