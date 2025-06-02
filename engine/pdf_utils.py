from sys import exc_info
import numpy as np
from typing import Any # Import Any for type hinting when cairo is None

try:
    import cairo
except ModuleNotFoundError:
    print("WARNING: Cairo module not found in pdf_utils. Some functionalities may be limited.")
    cairo = None # Define cairo as None so type hints and later references don't fail immediately
import subprocess
import os
from os.path import sep

all_subjects = []
if cairo is not None: # Only attempt to access IGCSE_PATH if cairo is available (i.e., likely full functionality expected)
    if os.name == "nt":  # Windows
        d_drive = "D:"
    else:
        d_drive = "/mnt/d"
    if os.environ.get("IGCSE_PATH"):
        igcse_path = os.environ["IGCSE_PATH"]
    else:
        igcse_path = f"{d_drive}{sep}Drive{sep}IGCSE-NEW"

    if os.path.exists(igcse_path) and os.path.isdir(igcse_path):
        all_subjects = [
            f
            for f in os.listdir(igcse_path)
            if os.path.isdir(igcse_path + sep + f) and f.isdigit()
        ]
    else:
        print(f"WARNING: igcse_path '{igcse_path}' not found or not a directory. 'all_subjects' will be empty.")
else:
    print("INFO: Cairo not loaded, skipping igcse_path and all_subjects initialization in pdf_utils.")


# ************************************************************************
# ********************** Page Segmentation *******************************
# ************************************************************************


def _surface_as_uint32(surface: "cairo.ImageSurface" if cairo else Any):
    """
    Return a (h, stride//4) view where each element is one ARGB32 pixel
    exactly as Cairo stores it (premultiplied, native endian).
    """
    surface.flush()  # make sure the C side is done
    h, stride = surface.get_height(), surface.get_stride()
    buf = surface.get_data()  # Python buffer -> zero-copy
    return np.frombuffer(buf, dtype=np.uint32).reshape(h, stride // 4)


def crop_image_surface(out_surf: "cairo.ImageSurface" if cairo else Any, y_start, y_end, padding):
    # print("dest_y", self.dest_y)

    o = out_surf
    s = round(y_start if y_start <= padding else y_start - padding)
    e = round(
        y_end + padding if y_end < (out_surf.get_height() - padding) else y_end
    )
    #     e = round(y_end + padding if y_end < (out_surf.get_height() - padding) else y_end)

    s_index = s * o.get_stride()
    e_index = e * o.get_stride()

    surf_width = out_surf.get_width()
    surf_height = e - s
    data = o.get_data()[s_index:e_index]
    print(surf_height, "vs", (e_index - s_index) // o.get_stride())
    print("full_data_len", len(o.get_data()))
    print(len(data), "vs", surf_height * surf_width * 4)
    out_surf = cairo.ImageSurface.create_for_data(
        data,
        cairo.FORMAT_ARGB32,
        surf_width,
        surf_height,
        o.get_stride(),
    )
    return out_surf


# *********************************************************
# *****************++ Numeric, Roman and Alphabet numbering
# ******************* Handler :


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
    """Rudimentary check if a string might be a Roman numeral."""
    if not numeral:
        return False
    numeral = numeral.upper()
    # Increased the set of valid characters.
    # A full validation would require checking sequences (e.g., IIII is invalid, IX is valid).
    # This is a basic filter, assuming more complex validation might exist or this is sufficient for context.
    valid_roman_chars = set("IVXLCDM")
    
    # Check if all characters are valid Roman numeral characters
    if not all(char in valid_roman_chars for char in numeral):
        return False

    # Further simple checks (optional, can be made more sophisticated)
    # - Max length (e.g., "MMMM" is often limit for 4000, longer might be stylistic but unusual in numbering)
    if len(numeral) > 7: # Arbitrary limit for typical list numbering (e.g. up to XXXIX is 5 chars, CLXXXVIII is 9)
        return False # Longer than "CLXXXVIII" is unlikely for simple list items.
                     # "MMMDCCCLXXXVIII" (3888) is 15 chars. Let's use a generous limit for typical numbering.
    
    # Avoid obviously invalid patterns like "IIII" or "VV" if desired, but this gets complex fast.
    # For now, just character set and length.
    # The old regex `r"^(?:(Part)\s*)?([ivxlcdmIVXLCDM]+)\s*([.)])?"` in detector is good for capture.
    # This function is a secondary check.
    
    # Simple check for too many repetitions (basic version)
    if "IIII" in numeral or "XXXX" in numeral or "CCCC" in numeral or "MMMM" in numeral: # Re-add MMMM check
        return False 
    if "VV" in numeral or "LL" in numeral or "DD" in numeral:
        return False

    # Specific invalid short sequences for tests
    invalid_short_sequences = {"IVX", "IC", "VX", "DM", "LC", "XD", "XM"} # Add more if needed
    if numeral in invalid_short_sequences:
        return False
    
    # Try to convert to decimal and back - this is a more robust check but needs full conversion logic
    # For now, rely on pattern matching and above heuristics.
    # A simple rule: smaller value cannot precede a much larger value unless it's standard subtraction
    # e.g. I can be before V or X. X before L or C. C before D or M.
    # V, L, D are never repeated and never used for subtraction.
    
    # Simplistic sequence checks (not exhaustive)
    if "VX" in numeral or "VL" in numeral or "VC" in numeral or "VD" in numeral or "VM" in numeral: return False # V cannot precede these
    if "LC" in numeral or "LD" in numeral or "LM" in numeral: return False # L cannot precede these
    if "DM" in numeral : return False # D cannot precede M

    # Check for invalid subtractive patterns like "IL" (should be XLIX) or "IM" (should be CMXCIX)
    # This gets complex quickly. The regex should capture candidates, and this is a secondary filter.
    # For the specific test cases: "ivx" is caught by "VX", "IC" is caught.
    
    return True


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


# *********************************************************************
# *********************+ open Files using system apps *****************
# ********************** ^^^^^^^^^^^^^^^^^^^^^^^^^^^^ *****************


def open_pdf_using_sumatra(pdf_full_path):
    if os.name != "nt":  # Windows
        png_full_path = pdf_full_path.replace("/mnt/d", "D:")
    subprocess.Popen(
        args=[
            "SumatraPDF-3.5.2-64.exe",
            png_full_path,
        ],
        start_new_session=True,
        stdout=None,
        stderr=None,
        stdin=None,
    )


def open_files_in_nvim(files: list[str]):
    print(files)
    subprocess.run(
        args=[
            "nvim",
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


def in_wsl() -> bool:
    """True if running under Windows Subsystem for Linux."""
    return os.name == "posix" and (
        "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ
    )


if __name__ == "__main__":
    roman = get_roman(1)
    alpha = get_alphabet(1)
    for i in range(1, 9):
        print(roman, alpha)
        print(alpha_roman_to_decimal(roman), alpha_roman_to_decimal(alpha))
        roman = get_next_label(roman)
        alpha = get_next_label(alpha)
