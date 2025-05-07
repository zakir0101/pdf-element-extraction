import os

# import sys
from typing import Tuple
import cairo
import json
from PyPDF2.generic import PdfObject, IndirectObject
from PyPDF2 import PdfReader

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


# CURR_ENCODING = ADBC

# from PyPDF2.fontTools.agl import AGL2UV  # Standard Adobe Glyph List
# from fontTools.encodings.symbol import encoding as symbol_encoding

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
        if "/DescendantFonts" in font_dict:
            self.is_composite = True
            des = font_dict.get("/DescendantFonts")
            for d in des:
                if d and isinstance(d, IndirectObject):
                    font_dict.update(reader.get_object(d))
                    # pprint.pprint(font_dict)

        self.font_object = font_dict
        self.font_name: str = font_name
        self.base_font: str = str(font_dict.get("/BaseFont"))
        self.font_type: str = str(font_dict.get("/Subtype"))
        self.first_char: int = int(font_dict.get("/FirstChar", 1))
        self.last_char: int = int(font_dict.get("/LastChar", -1))

        if not self.is_composite:
            widths = font_dict.get("/Widths", [])
            self.widths: list[int] = [int(x) for x in widths]
        else:
            widths = font_dict.get("/W", [])
            key = 0
            self.widths = {}
            for el in widths:
                if isinstance(el, list):
                    self.widths[key] = el[0]
                else:
                    key = int(el)

        self.encoding = font_dict.get("/Encoding")
        self.ft_encoding = None
        if isinstance(self.encoding, IndirectObject):
            self.font_diff: PdfObject | None = reader.get_object(
                self.encoding
            ).get("/Differences")
            self.diff_map = self.map_diff_encoding()

        else:
            self.font_diff = None
            self.diff_map = {}
        self.unicode_map = {}
        self.load_unicode_map()

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
            # print("FontDescriptor EXIXT for font ", font_path)

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
                                # print(
                                #     f"Error setting font {font_name} to enc: {enc}"
                                # )
                        if self.ft_encoding is None:
                            self.ft_face.set_charmap(self.ft_face.charmaps[0])
                            self.ft_encoding = self.ft_face.charmap.encoding

                        self.char_to_gid, self.symbol_to_gid = (
                            self.get_glyph_id_maps(font_path)
                        )

                    else:
                        self.ft_encoding = None

                    # print("hopla, font name is ", font_name)
                    # print("symbole_to_gid", self.symbol_to_gid)
                    # print("Font Saved successfully to", font_path)

        # Extract ToUnicode map if present
        self.is_math_font = "Math" in self.base_font
        # Check if it's a symbol font
        self.is_symbol_font = (
            self.base_font.endswith("Symbol")
            or font_dict.get("/Encoding") == "/Symbol"
        )
        self.to_unicode_map = {}
        if "/ToUnicode" in font_dict:
            tounicode = font_dict["/ToUnicode"]
            if isinstance(tounicode, IndirectObject):
                tounicode = reader.get_object(tounicode)

            cmap_data = tounicode.get_data().decode("utf-8")
            # print("found ToUnicode map")
            # print("ToUnicode map:", cmap_data)
            # Parse the CMap data to build unicode mapping
            # This needs proper CMap parsing...

        # Remove leading '/' and split into parts
        parts = self.base_font.lstrip("/").split("+", 1)
        if len(parts) == 2:
            prefix, font_name = parts
        else:
            font_name = parts[0]

        # Split font name into family and style
        font_parts = font_name.split(",")
        self.family = None
        if len(font_parts) > 1:
            self.family = font_parts[0]

        if not self.family or self.family.lower() == "symbol":
            self.family = "Sans"  # Fallback to Sans
        self.style = font_parts[1:] if len(font_parts) > 1 else font_parts
        self.style = list(map(str.lower, self.style))

        self.slant = cairo.FONT_SLANT_NORMAL
        self.weight = cairo.FONT_WEIGHT_NORMAL
        for style_part in self.style:
            style = style_part.lower()
            if "italic" in style:
                self.slant = cairo.FONT_SLANT_ITALIC
            elif "oblique" in style:
                self.slant = cairo.FONT_SLANT_OBLIQUE
            if "bold" in style:
                self.weight = cairo.FONT_WEIGHT_BOLD
                # print(f"font {self.font_name} was set to bold")
        # print(
        #     f"font : {self.font_name} has family {self.family} and style {self.style} and base font {self.base_font}"
        # )

    def get_glyph_id_maps(self, font_path):
        char_to_gid = {}
        symbol_to_gid = {}
        for cp, raw_gid in self.ft_face.get_chars():  # iterate the cmap
            char = chr(cp)

            gname0 = self.diff_map.get(cp, "").replace("/", "")
            if self.ft_face._has_glyph_names():
                try:
                    gname = self.ft_face.get_glyph_name(raw_gid).decode(
                        "ascii"
                    )
                except Exception:
                    gname = ""
            elif not gname:
                gname = self.get_symbol_name_from_char_code(cp)

            if raw_gid > 0:
                char_to_gid[char] = raw_gid
                if gname0:
                    symbol_to_gid[gname0] = raw_gid
                if gname and gname != ".notdef":
                    symbol_to_gid[gname] = raw_gid
        return char_to_gid, symbol_to_gid

    def get_symbol_name_from_char_code(self, char_code):

        symbol = UV2AGL.get(char_code, None)
        if not symbol and char_code < len(winansi_encoding):
            symbol = winansi_encoding[char_code]
        if symbol:
            return symbol.lstrip("/")
        else:
            return "<unavailable>"

    def get_cairo_font_face(self):
        """Get a Cairo font face from the embedded font if available"""
        # if not self.ft_encoding:
        #     self.ft_encoding = None
        self.font_face = create_cairo_font_face_for_file(
            self.font_path, encoding=self.ft_encoding
        )
        return self.font_face

    def load_unicode_map(self):
        path = f"engine{sep}agl_list.txt"
        if not os.path.exists(path):
            raise FileNotFoundError("AGL list file not found")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith("#"):
                    continue
                agl_code, unicode = line.split(";")
                self.unicode_map[agl_code] = unicode.strip()

    def map_diff_encoding(self, debug=False):
        # LATER:
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

    # def get_unicode(self, diff_code: str) -> Tuple[str, int | None]:
    #     diff_code = diff_code.lstrip("\\")
    #     char_code = int(diff_code, 8)
    #     width = self.get_char_width_from_code(char_code)
    #
    #     if self.diff_map is None:
    #         return self.get_default_ansi(char_code), width
    #
    #     char_symbol = self.diff_map.get(char_code)
    #     if not char_symbol:
    #         return self.get_default_ansi(char_code), width
    #
    #     char_symbol = char_symbol.lstrip("/")
    #
    #     unicode_value = None
    #
    #     if self.is_math_font:
    #         # WHERE DO WE GET MATH MAPPINGS FROM?
    #         unicode_value = math_symbols.get(char_symbol)
    #     elif self.is_symbol_font:
    #         unicode_value = symbol_encoding.get(char_symbol)
    #     else:
    #         unicode_value = AGL2UV.get(char_symbol)
    #
    #     if unicode_value is None:
    #         print(
    #             f"No mapping found for {char_symbol} in font {self.font_name}"
    #         )
    #         return self.get_default_ansi(char_code), width
    #
    #     return chr(unicode_value), width

    def get_char_code(self, diff_code: str) -> Tuple[int, int]:

        diff_code = diff_code.lstrip("\\")
        char_code = int(diff_code, 8)
        width = self.get_char_width_from_code(char_code)
        return char_code, width

    def get_unicode(self, diff_code: str) -> Tuple[str, int | None]:
        # parse unicode as octal number
        char_code, width = self.get_char_code(diff_code=diff_code)
        if self.diff_map is None:
            # print(
            #     f"No difference encoding map found for font {self.font_name} , char_code is {char_code},  diff code {diff_code}"
            # )
            return self.get_default_ansi(char_code), width, char_code

        char_symbol = self.diff_map.get(char_code)
        if not char_symbol:
            print(
                f"Symbol not found for {char_code}, from diff code {diff_code}"
            )
            return self.get_default_ansi(char_code), width, char_code
        char_symbol = char_symbol.lstrip("/")
        unicode_value = self.unicode_map.get(
            char_symbol.replace("lpar", "lparen").replace("rpar", "rparen")
        )
        if not unicode_value:
            # print(f"Unicode not found for {char_symbol}")
            return self.get_default_ansi(char_code), width, char_code

        value = json.loads(f'"\\u{unicode_value}"')
        return value, width, char_code

    def get_default_ansi(self, char_code_base_10: int):
        return bytearray([char_code_base_10]).decode("ansi")

    def get_char_width(self, char: str):
        # if len(self.widths) == 1:
        #     return self.widths[0]
        char_code = ord(char.encode(ansi))
        return self.get_char_width_from_code(char_code)

    def get_char_width_from_code(self, char_code: int):
        if char_code >= self.first_char and char_code <= self.last_char:
            return self.widths[char_code - self.first_char]
        return None

    # def verify_embedded_font_loading(
    #     self, font_file_key, font_desc, font_data, tmp_file_path, debug=False
    # ):
    #     """
    #     Verify and load an embedded font
    #
    #     Args:
    #         font_file_key: Key of the font file (/FontFile, /FontFile2, or /FontFile3)
    #         font_desc: Font descriptor dictionary
    #         font_data: Raw font data bytes
    #         tmp_file_path: Path to the temporary file containing the font data
    #
    #     Returns:
    #         tuple: (embedded_font_object, glyphs_names)
    #     """
    #     try:
    #         if debug:
    #             print(f"Attempting to load embedded font: {font_file_key}")
    #             print(f"Font descriptor type: {font_desc.get('/Subtype')}")
    #             print(f"Font data length: {len(font_data)} bytes")
    #
    #         if (
    #             font_file_key == "/FontFile3"
    #             and font_desc.get("/Subtype") == "/Type1C"
    #         ):
    #             from fontTools.cffLib import CFFFontSet
    #
    #             try:
    #                 cff = CFFFontSet()
    #                 cff.decompile(font_data, None)
    #
    #                 font_name = list(cff.keys())[0]
    #                 font = cff[font_name]
    #                 glyphs_names = list(font.CharStrings.keys())
    #                 if debug:
    #                     print("CFF font loaded successfully")
    #                     print(f"First 100 glyph names: {glyphs_names[:100]}")
    #                 return cff, glyphs_names
    #             except Exception as e:
    #                 if debug:
    #                     print(f"Failed to load Type1C/CFF font: {e}")
    #                 return None, []
    #
    #         elif font_file_key == "/FontFile":
    #             if debug or True:
    #                 print("Type1 font detected, limited support available")
    #             return None, []
    #
    #         else:
    #             is_ttf = False
    #
    #             try:
    #                 with open(tmp_file_path, "rb") as f:
    #                     signature = f.read(4)
    #                     if signature in (
    #                         b"\x00\x01\x00\x00",
    #                         b"OTTO",
    #                         b"true",
    #                         b"typ1",
    #                     ):
    #                         is_ttf = True
    #                         if debug:
    #                             print(
    #                                 f"Valid font signature detected: {signature}"
    #                             )
    #                     else:
    #                         if debug:
    #                             print(
    #                                 f"Warning: Not a standard TTF/OTF signature: {signature}"
    #                             )
    #
    #                 if is_ttf:
    #                     try:
    #                         font = TTFont(
    #                             tmp_file_path,
    #                             fontNumber=0,
    #                             lazy=True,
    #                             checkChecksums=False,
    #                             ignoreDecompileErrors=True,
    #                         )
    #
    #                         glyphs = []
    #                         glyphs = font.getGlyphNames()
    #
    #                     except Exception as e:
    #                         if debug or True:
    #                             print(
    #                                 f"Failed to load TrueType/OpenType font with TTFont: {e}"
    #                             )
    #                         return None, []
    #                 else:
    #                     if debug:
    #                         print(
    #                             "Skipping font loading - not a supported font format"
    #                         )
    #                     return None, []
    #             except Exception as e:
    #                 if debug:
    #                     print(f"Failed to load TrueType/OpenType font: {e}")
    #                     print(f"Font signature check: {is_ttf}")
    #                 return None, []
    #
    #     except Exception as e:
    #         if debug:
    #             print(f"Exception loading embedded font: {e}")
    #         import traceback
    #
    #         traceback.print_exc()
    #         return None, []
