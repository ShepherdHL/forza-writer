"""Text layout math ported from KFPS editor.js buildTextVinylForzaLetterShapes."""

from forza_writer.shapes import char_to_resource, resource_to_shape_word, resource_to_typecode

PIXEL_ART_SQUARE_SIZE = 128.498032


def layout_forza_text(
    text: str,
    font: int = 1,
    target_height: float = 360.0,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> list[dict]:
    """
    Returns list of shape dicts ready for JSON export.
    target_height: total height of the text block in editor units
    center_x/y: center anchor point
    """
    lines = text.replace("\r\n", "\n").split("\n")
    line_height = target_height / max(1, len(lines))
    glyph_height = line_height * 0.82
    scale = glyph_height / PIXEL_ART_SQUARE_SIZE
    advance = glyph_height * 0.72
    line_gap = line_height * 0.18
    total_height = len(lines) * line_height - line_gap

    shapes: list[dict] = []
    for line_index, line in enumerate(lines):
        line_width = 0.0
        for char in line:
            if char == " ":
                line_width += advance * 0.58
            elif char_to_resource(char, font):
                line_width += advance
            else:
                line_width += advance * 0.5

        cursor = center_x - line_width / 2
        y = center_y - total_height / 2 + line_index * line_height + glyph_height / 2

        for char in line:
            if char == " ":
                cursor += advance * 0.58
                continue
            resource = char_to_resource(char, font)
            char_advance = advance if resource else advance * 0.5
            if resource:
                family, index = resource
                shapes.append(
                    {
                        "type": resource_to_typecode(family, index),
                        "type_word": resource_to_shape_word(family, index),
                        "data": [
                            round(cursor + char_advance / 2, 6),
                            round(-y, 6) or 0.0,
                            round(scale, 6),
                            round(scale, 6),
                            0.0,
                            0.0,
                            0,
                        ],
                        "color": [255, 255, 255, 255],
                    }
                )
            cursor += char_advance

    return shapes
