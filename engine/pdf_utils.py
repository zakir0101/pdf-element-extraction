import numpy as np

OPAQUE_WHITE = 0xFFFFFFFF
ANY_ALPHA0_WHITE = 0x00FFFFFF  # alpha 0 + white RGB


import numpy as np  # speeds things up; pure-Python fallback shown later


def _surface_as_uint32(surface):
    """
    Return a (h, stride//4) view where each element is one ARGB32 pixel
    exactly as Cairo stores it (premultiplied, native endian).
    """
    surface.flush()  # make sure the C side is done
    h, stride = surface.get_height(), surface.get_stride()
    buf = surface.get_data()  # Python buffer -> zero-copy
    return np.frombuffer(buf, dtype=np.uint32).reshape(h, stride // 4)


def row_is_blank(
    row, usable_cols, white=OPAQUE_WHITE, twhite=ANY_ALPHA0_WHITE
):
    # all() on the first width pixels; ignore the padding on the right edge
    part = row[:usable_cols]
    return np.all((part == white) | (part == twhite))


def build_blank_mask(surface):
    pix = _surface_as_uint32(surface)
    w = surface.get_width()
    return np.fromiter(
        (row_is_blank(r, w) for r in pix), dtype=bool, count=pix.shape[0]
    )


def get_segments(surface, min_y, max_y, min_h):
    gaps = find_horizontal_gaps(surface, min_y, min_h)
    segments = []
    cursor = min_y
    for gy, gh in gaps:
        if gy > cursor:  # rows before the gap
            segments.append((cursor, gy - cursor))
        cursor = gy + gh  # skip the gap

    if cursor < max_y:  # rows after the last gap
        segments.append((cursor, max_y - cursor))
    return segments


def find_horizontal_gaps(surface, min_y, min_h):
    mask = build_blank_mask(surface)  # True ↔ blank
    gaps, h_px = [], len(mask)

    start = None
    for y, blank in enumerate(mask):
        if blank and start is None:
            start = y
        elif not blank and start is not None:
            gaps.append((start, y - start))
            start = None
    if start is not None:  # ran off bottom still in blank
        gaps.append((start, h_px - start))

    # translate back to PDF user-space if you like
    # scale = dpi / 72.0
    # page_h_pt = h_px / scale
    gaps = [(y, h) for y, h in gaps if h > min_h and y > min_y]
    # return gaps[-1] if len(gaps) > 0 else (None, 0)
    return gaps


def get_alphabet(number):
    # index = ord('a') + (number - 1 )
    return chr(number - 1 + 97)


def get_roman(number):
    num = [1, 4, 5, 9, 10, 40, 50, 90, 100, 400, 500, 900, 1000]
    sym = [
        "I",
        "IV",
        "V",
        "IX",
        "X",
        "XL",
        "L",
        "XC",
        "C",
        "CD",
        "D",
        "CM",
        "M",
    ]
    i = 12
    # number = number + 1
    result = ""
    while number:
        div = number // num[i]
        number %= num[i]

        while div:
            result += sym[i]
            div -= 1
        i -= 1

    return result.lower()


def checkIfRomanNumeral(numeral: str):
    """Controls that the userinput only contains valid roman numerals"""
    numeral = numeral.upper()
    validRomanNumerals = ["X", "V", "I"]
    valid = True
    for letters in numeral:
        if letters not in validRomanNumerals:
            valid = False
            break
    return valid


def value(r):
    if r == "I":
        return 1
    if r == "V":
        return 5
    if r == "X":
        return 10
    if r == "L":
        return 50
    if r == "C":
        return 100
    if r == "D":
        return 500
    if r == "M":
        return 1000
    return -1


def romanToDecimal(str):
    res = 0
    i = 0

    while i < len(str):
        # Getting value of symbol s[i]
        s1 = value(str[i])

        if i + 1 < len(str):
            # Getting value of symbol s[i + 1]
            s2 = value(str[i + 1])

            # Comparing both values
            if s1 >= s2:
                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s1
                i = i + 1
            else:
                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s2 - s1
                i = i + 2
        else:
            res = res + s1
            i = i + 1

    return res


def alpha_roman_to_decimal(charac):
    """
    convert alpha / roman number to decimals , starting from 0 == a or i
    """
    is_roman = checkIfRomanNumeral(charac)
    if is_roman:
        num = romanToDecimal(charac.upper())
    elif len(charac) == 1:
        num = ord(charac) - 96
    else:
        raise Exception
    return num - 1


def get_next_label_old(prev: str):
    is_roman = checkIfRomanNumeral(prev)
    if is_roman:
        num = romanToDecimal(prev.upper())
        next = get_roman(num + 1)
    elif len(prev) == 1:
        num = ord(prev)
        next = get_alphabet(num - 96 + 1)
    else:
        raise Exception
    return next


NUMERIC = 1
ALPHAPET = 2
ROMAN = 3


def get_next_label(prev, system):
    prev = str(prev)
    if prev.isdigit() and system == NUMERIC:
        prev = int(prev)
        prev += 1
        return prev
    elif type(prev) is str and system == ROMAN:
        num = romanToDecimal(prev.upper())
        return get_roman(num + 1)
    elif type(prev) is str and len(prev) == 1 and system == ALPHAPET:
        num = ord(prev)
        return get_alphabet(num - 96 + 1)
    else:
        raise Exception


def is_first_label(input: str):
    return input == "i" or input == "a"


if __name__ == "__main__":
    roman = get_roman(1)
    alpha = get_alphabet(1)
    for i in range(1, 9):
        print(roman, alpha)
        print(alpha_roman_to_decimal(roman), alpha_roman_to_decimal(alpha))
        roman = get_next_label(roman)
        alpha = get_next_label(alpha)
