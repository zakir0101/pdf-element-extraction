from math import isnan
import os
from .pdf_encoding import PdfEncoding as pnc

from typing import Tuple
import cairo
import json
from pypdf.generic import PdfObject, IndirectObject
from pypdf import PdfReader

from .pdf_utils import open_image_in_irfan, kill_with_taskkill
from engine import winansi
from .create_cairo_font import create_cairo_font_face_for_file
import pprint

# from fontTools.ttLib import TTFont
from os.path import sep
from fontTools.agl import UV2AGL
import freetype

from .winansi import winansi_encoding

UNIC = freetype.FT_ENCODINGS.get("FT_ENCODING_UNICODE")
ADBC = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_CUSTOM")
ADBS = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_STANDARD")
ADBE = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_EXPERT")
ADBL = freetype.FT_ENCODINGS.get("FT_ENCODING_ADOBE_LATIN1")

ENC_LIST = [ADBC, ADBE, ADBS, ADBL, UNIC]


if os.name == "nt":  # Windows
    ansi = "ansi"
else:
    ansi = "iso_8859_1"


class PdfFont:

    def __init__(
        self, font_name: str, font_object: PdfObject | None, reader: PdfReader
    ) -> None:

        if font_object is None:
            raise ValueError("Font object is None")
        font_dict = {
            key: value
            for key, value in font_object.items()
            if not key.startswith("_")
        }
        self.is_composite = False
        self.descendents = []
        if "/DescendantFonts" in font_dict:

            # print("\n\n\n*********************************************")
            # pprint.pprint(font_dict)
            # print("\n\n")
            self.is_composite = True
            des = font_dict.get("/DescendantFonts")
            if not isinstance(des, list):
                des = reader.get_object(des)
            for d in des:
                if d and isinstance(d, IndirectObject):
                    d = reader.get_object(d)
                font_dict.update(d)
                self.descendents.append(d)
                # pprint.pprint(d)

        self.font_object = font_dict
        self.font_name: str = font_name
        self.base_font: str = str(font_dict.get("/BaseFont"))
        self.font_type: str = str(font_dict.get("/Subtype"))
        self.first_char: int = int(font_dict.get("/FirstChar", 1))
        self.last_char: int = int(font_dict.get("/LastChar", -1))

        if not self.is_composite:
            widths = font_dict.get("/Widths")
            if isinstance(widths, IndirectObject):
                widths = reader.get_object(widths)
            self.font_widths = None
            if isinstance(widths, list):
                if len(widths) > 1:
                    self.widths: list[int] = [int(x) for x in widths]
                else:
                    widths = widths[0]
            if isinstance(widths, (int, float, str)):
                self.widths = widths
            if self.widths is None:
                raise Exception
        else:
            self.default_width = font_dict.get("/DW", 1000)
            widths = font_dict.get("/W", [])
            if isinstance(widths, IndirectObject):
                widths = reader.get_object(widths)
            # key = 0
            self.widths = {}
            i = 0
            while i < len(widths) - 1:
                el = int(widths[i])
                n_el = widths[i + 1]
                if isinstance(n_el, list):
                    for j in range(len(n_el)):
                        self.widths[el + j] = n_el[j]
                    i = i + 2
                elif i + 2 < len(widths):
                    n_el = int(n_el)
                    n2_el = widths[i + 2]
                    if isinstance(n2_el, list):
                        if len(n2_el) == 1:
                            n2_el = n2_el[0]
                        else:
                            raise Exception
                    for j in range(el, n_el + 1):
                        self.widths[j] = n2_el
                    i = i + 3

        self.encoding = font_dict.get("/Encoding")
        self.ft_encoding = None
        if isinstance(self.encoding, IndirectObject):
            self.font_diff: PdfObject | None = reader.get_object(
                self.encoding
            ).get("/Differences")
            self.diff_map = self.create_diff_map_dict()

        else:
            self.font_diff = None
            self.diff_map = {}

        self.temp_dir = "temp"
        font_path = (
            self.temp_dir
            + sep
            + font_name
            + "_"
            + str(self.first_char)
            + ".ttf"
        )
        self.font_path = font_path
        if not os.path.exists(self.temp_dir):
            os.mkdir(self.temp_dir)
        elif os.path.exists(font_path):
            os.remove(font_path)

        self.font_face = None
        self.embedded_font = None
        if "/FontDescriptor" in font_dict:

            font_desc = font_dict["/FontDescriptor"]
            if isinstance(font_desc, IndirectObject):
                font_desc = reader.get_object(font_desc)
            self.missing_width = font_desc.get("/MissingWidth")
            # Check for embedded font data
            for font_file_key in ["/FontFile", "/FontFile2", "/FontFile3"]:
                if font_file_key in font_desc:
                    font_file = font_desc[font_file_key]
                    if isinstance(font_file, IndirectObject):
                        font_file = reader.get_object(font_file)

                    font_data = font_file.get_data()
                    file = open(font_path, "bw")
                    file.write(font_data)
                    file.flush()
                    file.close()

                    self.ft_face = freetype.Face(font_path)
                    self.ft_encoding = None
                    if not self.is_composite:
                        for enc in ENC_LIST:
                            try:
                                self.ft_face.select_charmap(enc)
                                self.ft_encoding = enc
                                break
                            except Exception as e:
                                pass
                        if self.ft_encoding is None:
                            self.ft_face.set_charmap(self.ft_face.charmaps[0])
                            self.ft_encoding = self.ft_face.charmap.encoding

                        (
                            self.cid_to_gid,
                            self.char_to_gid,
                            self.symbol_to_gid,
                        ) = self.create_glyph_map_dicts(font_path)
                    else:
                        self.ft_encoding = None

        # Extract ToUnicode map if present
        self.is_math_font = "Math" in self.base_font
        # Check if it's a symbol font
        self.is_symbol_font = (
            self.base_font.endswith("Symbol")
            or font_dict.get("/Encoding") == "/Symbol"
        )
        self.cid_to_unicode = {}
        self.valid_ranges = None
        if "/ToUnicode" in font_dict:
            tounicode = font_dict["/ToUnicode"]
            if isinstance(tounicode, IndirectObject):
                tounicode = reader.get_object(tounicode)

            self.cmap_data = tounicode.get_data().decode("utf-8")
            self.cid_to_unicode, self.valid_ranges = (
                self.create_tounicode_map_dict(self.cmap_data)
            )
            # self.debug_font()

        # parts = self.base_font.lstrip("/").split("+", 1)
        # if len(parts) == 2:
        #     prefix, font_name = parts
        # else:
        #     font_name = parts[0]

        # font_parts = font_name.split(",")
        # self.family = None
        # if len(font_parts) > 1:
        #     self.family = font_parts[0]

        # if not self.family or self.family.lower() == "symbol":
        #     self.family = "Sans"  # Fallback to Sans

        # self.style = font_parts[1:] if len(font_parts) > 1 else font_parts
        # self.style = list(map(str.lower, self.style))

        # self.slant = cairo.FONT_SLANT_NORMAL
        # self.weight = cairo.FONT_WEIGHT_NORMAL
        # for style_part in self.style:
        #     style = style_part.lower()
        #     if "italic" in style:
        #         self.slant = cairo.FONT_SLANT_ITALIC
        #     elif "oblique" in style:
        #         self.slant = cairo.FONT_SLANT_OBLIQUE
        #     if "bold" in style:
        #         self.weight = cairo.FONT_WEIGHT_BOLD

    def is_char_code_valid(self, cid):
        if self.cid_to_gid.get(cid) is not None:
            return True
        if self.valid_ranges is None:
            return False
        for start, end in self.valid_ranges:
            if start <= cid <= end:
                return True
        return False

    def create_tounicode_map_dict(self, data):
        tokens = self.tokenize_cmap(data)
        cid_map = {}
        codespace_ranges = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == "begincodespacerange":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    # Parse <start> <end> pairs
                    start = int(tokens[i + 1], 16)
                    end = int(tokens[i + 4], 16)
                    codespace_ranges.append((start, end))
                    i += 6  # Skip past '<', start, '>', '<', end, '>'
                # Skip past "endcodespacerange"
                while i < len(tokens) and tokens[i] != "endcodespacerange":
                    i += 1
                i += 1
            elif token == "beginbfchar":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    cid = int(tokens[i + 1], 16)
                    unicode_char = bytes(int(tokens[i + 4], 16)).decode(
                        "utf-8"
                    )
                    cid_map[cid] = unicode_char
                    i += 6  # Skip '<', cid, '>', '<', unicode, '>'
            elif token == "beginbfrange":
                count = int(tokens[i - 1]) if i > 0 else 0
                i += 1
                for _ in range(count):
                    cid_start = int(tokens[i + 1], 16)
                    cid_end = int(tokens[i + 4], 16)
                    uni_start = int(tokens[i + 7], 16)
                    for offset in range(cid_end - cid_start + 1):
                        cid = cid_start + offset
                        cid_map[cid] = bytes(uni_start + offset).decode(
                            "utf-8"
                        )
                    i += 9  # Skip '<', start, '>', '<', end, '>', '<', uni_start, '>'
            i += 1
        return cid_map, codespace_ranges

    def tokenize_cmap(self, data):
        tokens = []
        current = []
        in_comment = False
        for char in data:
            if char == "%":
                in_comment = True
            if in_comment:
                if char == "\n":
                    in_comment = False
                continue
            if char.isspace():
                if current:
                    tokens.append("".join(current))
                    current = []
            elif char in "<>":
                if current:
                    tokens.append("".join(current))
                    current = []
                tokens.append(char)
            else:
                current.append(char)
        if current:
            tokens.append("".join(current))
        return tokens

    def create_glyph_map_dicts(self, font_path):
        char_to_gid = {}
        symbol_to_gid = {}
        code_to_gid = {}
        for cp, raw_gid in self.ft_face.get_chars():  # iterate the cmap

            if raw_gid == 0:
                continue

            code_to_gid[cp] = raw_gid
            gname0 = self.diff_map.get(cp, "").replace("/", "")

            if gname0:
                is_symbole = True
                symbol_to_gid[gname0] = raw_gid
                continue

            gname = None
            if self.ft_face._has_glyph_names():
                try:
                    gname = self.ft_face.get_glyph_name(raw_gid)
                    gname = pnc.bytes_to_string(gname)
                except Exception:
                    gname = ""
            elif not gname:
                gname = self.get_symbol_name_from_char_code(cp)

            if gname and gname != ".notdef":
                symbol_to_gid[gname] = raw_gid
            if cp <= 255:
                char = pnc.int_to_char(cp)
                if char_to_gid.get(char) is not None:
                    raise Exception("2 code with same char representation")
                char_to_gid[char] = raw_gid

        return code_to_gid, char_to_gid, symbol_to_gid

    def get_cairo_font_face(self):
        """Get a Cairo font face from the embedded font if available"""
        self.font_face = create_cairo_font_face_for_file(
            self.font_path, encoding=self.ft_encoding
        )
        return self.font_face

    def create_diff_map_dict(self, debug=False):
        current_index = 1
        diff_map = {}
        for symbole in self.font_diff:
            sym = symbole
            if isinstance(sym, int):
                current_index = sym  # if int(sym) > 0 else 1
            else:
                diff_map[current_index] = sym
                current_index += 1
        if debug:
            print(diff_map)
        return diff_map

    def get_char_code_from_match(
        self, char: str, symbol: str, prev_symbol: str
    ) -> Tuple[int, int]:
        if char is not None:
            char_code = pnc.char_to_int(char)
        elif not self.is_composite:
            symbol = symbol.lstrip("\\")
            char_code = int(symbol, 8)
        else:
            if prev_symbol is None:
                raise Exception("missing prev symbol in composite font")
            high_byte = int(prev_symbol.strip("\\"), 8)
            low_byte = int(symbol.strip("\\"), 8)
            char_code = (high_byte << 8) | low_byte
            pass

        return char_code

    def get_default_ansi(self, char_code_base_10: int):
        return bytearray([char_code_base_10]).decode("ansi")

    def get_char_width_from_code(self, char_code: int):
        if isinstance(self.widths, (int, float)):
            return self.widths
        if not self.is_composite:
            if char_code >= self.first_char and char_code <= self.last_char:
                return (
                    self.widths[char_code - self.first_char]
                    or self.missing_width
                )
            else:
                return None
                raise Exception(
                    f"char code {char_code}, for char {chr(char_code)} , does not have width mapping"
                )
        else:
            return self.widths.get(char_code) or self.default_width

    def get_glyph_id_from_char_code(self, char_code: int, is_symbol: bool):
        symbol_name = None
        if self.is_composite:
            glyph_id = char_code
            symbol_name = f"\\{char_code}"
        elif is_symbol:
            symbol_name = self.diff_map.get(char_code, "").replace(
                "/", ""
            ) or self.get_symbol_name_from_char_code(char_code)
            glyph_id = self.symbol_to_gid.get(symbol_name)
        else:
            glyph_id = self.cid_to_gid.get(char_code)

        return glyph_id, symbol_name

    def get_symbol_name_from_char_code(self, char_code):
        symbol = UV2AGL.get(char_code, None)
        if not symbol and char_code < len(winansi_encoding):
            symbol = winansi_encoding[char_code]
        if symbol:
            return symbol.lstrip("/")
        else:
            return "<unavailable>"

    def debug_font(self):
        print(f"\n\n****************** {self.font_name} ******************")
        print(f"               ****************** ")
        font_size = 20

        pen_x, glyphs = 20, []
        y = 30
        counter = 0
        curr_dict = (
            self.cid_to_gid if not self.is_composite else self.cid_to_unicode
        )
        for cid, gid_or_unic in curr_dict.items():
            # if not
            #     continue
            prefix = ""
            if counter % 12 == 0:
                y = y + 50
                pen_x = 20
                prefix = "\n"
            if self.is_composite:
                if gid_or_unic == " ":
                    gid_or_unic = "Space"
                print(f"{prefix}{gid_or_unic:7}", end=" ")
                gid = cid
            else:
                o = chr(cid)
                if o == " ":
                    o = "Space"
                print(f"{prefix}{o:>7}", end=" ")
                gid = gid_or_unic  # self.cid_to_gid[cid]

            glyphs.append(cairo.Glyph(gid, pen_x, y))
            pen_x += 50
            counter += 1
        if counter == 0:
            pprint.pprint(self.cmap_data)
            pprint.pprint(self.cid_to_unicode)
        face_cairo = self.get_cairo_font_face()
        width = 500
        height = y + 50

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()  # white bg
        ctx.set_font_size(font_size)
        ctx.set_font_face(face_cairo)
        ctx.set_source_rgb(0, 0, 0)  # black text

        ctx.show_glyphs(glyphs)
        out_png = f"output{sep}output.png"
        surface.write_to_png(out_png)
        open_image_in_irfan(out_png)
        a = input("\n\npress any key to continue")
        kill_with_taskkill()

    # def load_unicode_map(self):
    #     path = f"engine{sep}agl_list.txt"
    #     if not os.path.exists(path):
    #         raise FileNotFoundError("AGL list file not found")
    #     with open(path, "r", encoding="utf-8") as f:
    #         lines = f.readlines()
    #         for line in lines:
    #             if line.startswith("#"):
    #                 continue
    #             agl_code, unicode = line.split(";")
    #             self.unicode_map[agl_code] = unicode.strip()

    # def get_unicode(self, diff_code: str) -> Tuple[str, int | None]:
    #     # parse unicode as octal number
    #     char_code, width = self.get_char_code(diff_code=diff_code)
    #     if self.diff_map is None:
    #         return self.get_default_ansi(char_code), width, char_code
    #
    #     char_symbol = self.diff_map.get(char_code)
    #     if not char_symbol:
    #         return self.get_default_ansi(char_code), width, char_code
    #     char_symbol = char_symbol.lstrip("/")
    #     unicode_value = self.unicode_map.get(
    #         char_symbol.replace("lpar", "lparen").replace("rpar", "rparen")
    #     )
    #     if not unicode_value:
    #         return self.get_default_ansi(char_code), width, char_code
    #
    #     value = json.loads(f'"\\u{unicode_value}"')
    #     return value, width, char_code
