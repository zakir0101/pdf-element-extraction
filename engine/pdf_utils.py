import numpy as np
import cairo
import subprocess
import os
from os.path import sep

import numpy as np  # speeds things up; pure-Python fallback shown later


if os.name == "nt":  # Windows
    d_drive = "D:"
else:
    d_drive = "/mnt/d"
if os.environ.get("IGCSE_PATH"):
    igcse_path = os.environ["IGCSE_PATH"]
else:
    igcse_path = f"{d_drive}{sep}Drive{sep}IGCSE-NEW"

# jwggfg

all_subjects = [
    f
    for f in os.listdir(igcse_path)
    if os.path.isdir(igcse_path + sep + f) and f.isdigit()
]


def _surface_as_uint32(surface: cairo.ImageSurface):
    """
    Return a (h, stride//4) view where each element is one ARGB32 pixel
    exactly as Cairo stores it (premultiplied, native endian).
    """
    surface.flush()  # make sure the C side is done
    h, stride = surface.get_height(), surface.get_stride()
    buf = surface.get_data()  # Python buffer -> zero-copy
    return np.frombuffer(buf, dtype=np.uint32).reshape(h, stride // 4)


OPAQUE_WHITE = 0xFFFFFFFF
ANY_ALPHA0_WHITE = 0x00FFFFFF  # alpha 0 + white RGB


def row_is_blank_old(
    row, usable_cols, white=OPAQUE_WHITE, twhite=ANY_ALPHA0_WHITE
):
    # all() on the first width pixels; ignore the padding on the right edge
    part = row[:usable_cols]
    return np.all((part == white) | (part == twhite))


def row_is_blank(
    row, usable_cols, white=OPAQUE_WHITE, twhite=ANY_ALPHA0_WHITE
):
    # all() on the first width pixels; ignore the padding on the right edge
    part = row[:usable_cols]
    f1 = 0.15
    s_left = round(f1 * usable_cols)
    s_right = round((1 - f1) * usable_cols)
    middle = part[s_left:s_right]
    sides = np.concatenate((part[:s_left], part[s_right:]), axis=0)
    # print("right > usable_col", s_right, usable_cols)
    # print("side length = ", len(sides))
    # print("middle length = ", len(middle))
    is_side_almost_empty = (
        np.count_nonzero((sides == white) | (sides == twhite)) / len(sides)
    ) > 0.99
    is_middle_completly_empyty = np.all((middle == white) | (middle == twhite))

    # is_part_completly_empyty = np.all((part == white) | (part == twhite))
    # if (
    #     is_middle_completly_empyty != is_part_completly_empyty
    #     and is_side_almost_empty
    # ):
    #     print(usable_cols, len(middle))
    #     print(str(is_part_completly_empyty), str(is_middle_completly_empyty))
    return is_middle_completly_empyty and is_side_almost_empty


def row_is_blank_new(
    row,
    usable_cols,
    *,  # ← star makes kwargs only
    alpha_thresh=5,
    white_thresh=200,
    tolerate=0.2,
):
    """
    Return True if <= `tolerate` fraction of the inspected pixels are
    non-blank (tolerate small dirt).
    """
    part = row[:usable_cols]

    alpha = (part >> 24) & 0xFF
    red = (part >> 16) & 0xFF
    green = (part >> 8) & 0xFF
    blue = part & 0xFF

    transparent = alpha <= alpha_thresh
    nearly_white = (
        (alpha >= 255 - alpha_thresh)
        & (red >= white_thresh)
        & (green >= white_thresh)
        & (blue >= white_thresh)
    )

    blank_mask = transparent | nearly_white
    n_bad = (~blank_mask).sum()  # how many “dirty” pixels
    return n_bad <= tolerate * usable_cols


def build_blank_mask(surface):
    pix = _surface_as_uint32(surface)
    w = surface.get_width()
    return np.fromiter(
        (row_is_blank(r, w) for r in pix), dtype=bool, count=pix.shape[0]
    )


def get_segments(surface, min_y, max_y, d0, factor=0.1):
    min_g = d0 * factor
    min_h = 0
    gaps, norm_gaps = find_horizontal_gaps(surface, min_y, d0, min_g)
    # print("gaps_count ( normal/filterd) = ", len(norm_gaps), len(gaps))
    # print(norm_gaps)
    segments = []
    cursor = min_y
    for gy, gh in norm_gaps:
        if gy > cursor:  # rows before the gap
            h_curr = gy - cursor
            segments.append((cursor, h_curr, d0))
        cursor = gy + gh  # skip the gap

    if cursor < max_y:  # rows after the last gap
        # try:
        h_curr = max_y - cursor
        segments.append((cursor, h_curr, d0))

        # except Exception as e:
        #     print(max_y, cursor)
        #     segments.append((cursor, (max_y) - cursor))

    return segments


def find_horizontal_gaps(surface, min_y, char_h, min_h):
    mask = build_blank_mask(surface)  # True ↔ blank
    gaps, h_px = [], len(mask)
    MIN_COUNT = round(0.1 * char_h)  # int(0.5 * char_h)
    start = None
    not_blanck_count = 0
    blanck_count = 0
    is_blank_mode = True
    # if min_y == 0:
    start = min_y
    for y, blank in enumerate(mask):
        if blank:
            blanck_count += 1
            not_blanck_count = 0
        else:
            not_blanck_count += 1
            blanck_count = 0

        if blanck_count > MIN_COUNT:
            is_blank_mode = True
        elif not_blanck_count > MIN_COUNT:
            is_blank_mode = False

        if is_blank_mode and start is None:
            start = y
        elif not is_blank_mode and start is not None:
            gaps.append((start, y - start))
            start = None
    if start is not None:  # ran off bottom still in blank
        gaps.append((start, h_px - start))

    # translate back to PDF user-space if you like
    # scale = dpi / 72.0
    # page_h_pt = h_px / scale
    fgaps = [(y, h) for y, h in gaps if h > min_h and y > min_y]
    # return gaps[-1] if len(gaps) > 0 else (None, 0)
    return fgaps, gaps


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


SEP = os.path.sep


#  (venv) ➜  pdf-element-extraction git:(master) ✗  '/mnt/d/Drive/IGCSE/0580/exams/0580_s15_qp_11.pdf
def open_pdf_using_sumatra(pdf_full_path):
    if os.name != "nt":  # Windows
        png_full_path = pdf_full_path.replace("/mnt/d", "D:")
    subprocess.Popen(
        args=[
            f"SumatraPDF-3.5.2-64.exe",
            png_full_path,
        ],
        start_new_session=True,
        stdout=None,
        stderr=None,
        stdin=None,
    )


def open_files_in_nvim(files: list[str]):
    # if os.name != "nt":  # Windows
    #     png_full_path = pdf_full_path.replace("/mnt/d", "D:")
    # files = "   ".join(files)
    print(files)
    subprocess.run(
        args=[
            f"nvim",
            "-p10",
            *files,
        ],
        check=False,
        # start_new_session=True,
        # stdout=None,
        # stderr=None,
        # stdin=None,
    )


def open_image_in_irfan(img_path):
    c_prefix = "C:" if os.name == "nt" else "/mnt/c"
    png_full_path = "\\\\wsl.localhost\\Ubuntu" + os.path.abspath(img_path)
    if os.name != "nt":  # Windows
        png_full_path = png_full_path.replace("/", "\\")
    subprocess.Popen(
        args=[
            f"{c_prefix}{SEP}Program Files{SEP}IrfanView{SEP}i_view64.exe",
            png_full_path,
        ],
        start_new_session=True,
        stdout=None,
        stderr=None,
        stdin=None,
    )


def kill_with_taskkill():
    """Use Windows’ native taskkill (works from Windows or WSL)."""
    TARGET = "i_view64.exe"
    TARGET2 = "SumatraPDF-3.5.2-64.exe"
    cmd = ["taskkill.exe", "/IM", TARGET, "/F"]
    cmd = ["taskkill", "/IM", TARGET2, "/F"]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ****************** TEMP **********************
def paeth_predictor(a, b, c):
    """
    Calculates the Paeth predictor.
    a = left, b = above, c = upper-left.
    """
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    elif pb <= pc:
        return b
    else:
        return c


def unfilter_scanline(
    filter_type, scanline_data, prev_scanline_data, bytes_per_pixel
):
    """
    Applies the inverse of a PNG filter to a scanline.
    All additions are modulo 256.
    """
    recon = bytearray(len(scanline_data))  # Reconstructed scanline

    if filter_type == 0:  # None
        return scanline_data

    for i in range(len(scanline_data)):
        filt_x = scanline_data[i]

        if filter_type == 1:  # Sub
            recon_a = recon[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
            recon[i] = (filt_x + recon_a) & 0xFF
        elif filter_type == 2:  # Up
            prior_b = prev_scanline_data[i] if prev_scanline_data else 0
            recon[i] = (filt_x + prior_b) & 0xFF
        elif filter_type == 3:  # Average
            recon_a = recon[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
            prior_b = prev_scanline_data[i] if prev_scanline_data else 0
            recon[i] = (filt_x + ((recon_a + prior_b) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            recon_a = recon[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
            prior_b = prev_scanline_data[i] if prev_scanline_data else 0
            prior_c = (
                prev_scanline_data[i - bytes_per_pixel]
                if prev_scanline_data and i >= bytes_per_pixel
                else 0
            )
            paeth_val = paeth_predictor(recon_a, prior_b, prior_c)
            recon[i] = (filt_x + paeth_val) & 0xFF
        else:
            raise ValueError(f"Unknown filter type: {filter_type}")

    return bytes(recon)


if __name__ == "__main__":
    roman = get_roman(1)
    alpha = get_alphabet(1)
    for i in range(1, 9):
        print(roman, alpha)
        print(alpha_roman_to_decimal(roman), alpha_roman_to_decimal(alpha))
        roman = get_next_label(roman)
        alpha = get_next_label(alpha)
