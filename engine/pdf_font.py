import os
from typing import Tuple
import cairo
import json
from PyPDF2.generic import PdfObject, IndirectObject
from PyPDF2 import PdfReader
import sys
from fontTools.ttLib import TTFont
from fontTools.unicode import Unicode

# from PyPDF2.fontTools.agl import AGL2UV  # Standard Adobe Glyph List
# from fontTools.encodings.symbol import encoding as symbol_encoding


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
        self.font_object = font_dict
        self.font_name: str = font_name
        self.base_font: str = str(font_dict.get("/BaseFont"))
        self.font_type: str = str(font_dict.get("/Subtype"))
        self.first_char: int = int(font_dict.get("/FirstChar", 1))
        self.last_char: int = int(font_dict.get("/LastChar", -1))
        widths = font_dict.get("/Widths", [])
        self.widths: list[int] = [int(x) for x in widths]
        self.encoding = font_dict.get("/Encoding")
        if isinstance(self.encoding, IndirectObject):
            self.font_diff: PdfObject | None = reader.get_object(
                self.encoding
            ).get("/Differences")
            self.diff_map = self.map_diff_encoding()
        else:
            self.font_diff = None
            self.diff_map = None
        self.unicode_map = {}
        self.load_unicode_map()

        if "/FontDescriptor" in font_dict:
            font_desc = font_dict["/FontDescriptor"]
            if isinstance(font_desc, IndirectObject):
                font_desc = reader.get_object(font_desc)

            # Check for embedded font data
            for font_file_key in ["/FontFile", "/FontFile2", "/FontFile3"]:
                if font_file_key in font_desc:
                    font_file = font_desc[font_file_key]
                    if isinstance(font_file, IndirectObject):
                        font_file = reader.get_object(font_file)

                    # Get the raw font data
                    font_data = font_file.get_data()

                    # Save to temporary file for fontTools
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".ttf"
                    ) as tmp:
                        tmp.write(font_data)
                        tmp.flush()
                    # Replace the embedded font loading section (around line 70)
                    try:
                        pass
                        self.embedded_font, glyphs_names = (
                            self.verify_embedded_font_loading(
                                font_file_key, font_desc, font_data, tmp.name
                            )
                        )
                        # if glyphs_names:
                        #     print(
                        #         f"Loaded {len(glyphs_names)} glyphs from embedded font"
                        #     )
                    except Exception as e:
                        print(f"Could not load embedded font {font_name}: {e}")
                        self.embedded_font = None
                    # Clean up temp file

                    # Before cleaning up the file
                    # if hasattr(self.embedded_font, "close"):
                    #     self.embedded_font.close()
                    # try:
                    #     os.unlink(tmp.name)
                    # except Exception as e:
                    #     print(f"Error cleaning up temp file: {e}")

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
            print("found ToUnicode map")
            print("ToUnicode map:", cmap_data)
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
                print(f"font {self.font_name} was set to bold")
        # print(
        #     f"font : {self.font_name} has family {self.family} and style {self.style} and base font {self.base_font}"
        # )

    def get_cairo_font_face(self):
        """Get a Cairo font face from the embedded font if available"""
        if not hasattr(self, "embedded_font") or self.embedded_font is None:
            print("embeded font is NONE ")
            return None

        # if True or hasattr(self.embedded_font, "ttFont"):
        # For TTFont objects
        import tempfile
        import os
        from .create_cairo_font import (
            create_cairo_font_face_for_file,
        )

        # Create a temporary file with the font data
        print("hi")
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ttf")
            tmp.close()  # Close the file handle but don't delete the file yet

        except Exception as e:
            print(f"Failed to create temporary file: {e}")
            return None
        try:

            print("hallo")
            self.embedded_font.save(tmp.name)
            font_face = create_cairo_font_face_for_file(tmp.name)
            print(font_face)
            # Delete the temporary file after creating the font face
            os.unlink(tmp.name)
            return font_face
        except Exception as e:
            print(f"Failed to create Cairo font face: {e}")
            try:
                os.unlink(tmp.name)
            except:
                pass
            return None

        return None

    def load_unicode_map(self):
        path = "engine\\agl_list.txt"
        if not os.path.exists(path):
            raise FileNotFoundError("AGL list file not found")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith("#"):
                    continue
                agl_code, unicode = line.split(";")
                self.unicode_map[agl_code] = unicode.strip()

    def map_diff_encoding(self):
        # LATER:
        current_index = 1
        diff_map = {}
        for symbole in self.font_diff:
            sym: str = str(symbole)
            if sym.isnumeric():
                current_index = int(sym)
            else:
                diff_map[current_index] = sym
                current_index += 1
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

    def get_unicode(self, diff_code: str) -> Tuple[str, int | None]:
        # parse unicode as octal number

        diff_code = diff_code.lstrip("\\")
        char_code = int(diff_code, 8)
        width = self.get_char_width_from_code(char_code)
        if self.diff_map is None:
            # print(
            #     f"No difference encoding map found for font {self.font_name} , char_code is {char_code},  diff code {diff_code}"
            # )
            return self.get_default_ansi(char_code), width

        char_symbol = self.diff_map.get(char_code)
        if not char_symbol:
            print(
                f"Symbol not found for {char_code}, from diff code {diff_code}"
            )
            return self.get_default_ansi(char_code), width
        char_symbol = char_symbol.lstrip("/")
        unicode_value = self.unicode_map.get(
            char_symbol.replace("lpar", "lparen").replace("rpar", "rparen")
        )
        if not unicode_value:
            print(f"Unicode not found for {char_symbol}")
            return self.get_default_ansi(char_code), width

        value = json.loads(f'"\\u{unicode_value}"')
        return value, width

    def get_default_ansi(self, char_code_base_10: int):
        return bytearray([char_code_base_10]).decode("ansi")

    def get_char_width(self, char: str):
        # if len(self.widths) == 1:
        #     return self.widths[0]
        char_code = ord(char.encode("ansi"))
        return self.get_char_width_from_code(char_code)

    def get_char_width_from_code(self, char_code: int):
        if char_code >= self.first_char and char_code <= self.last_char:
            return self.widths[char_code - self.first_char]
        return None

    def verify_embedded_font_loading(
        self, font_file_key, font_desc, font_data, tmp_file_path, debug=False
    ):
        """
        Verify and load an embedded font

        Args:
            font_file_key: Key of the font file (/FontFile, /FontFile2, or /FontFile3)
            font_desc: Font descriptor dictionary
            font_data: Raw font data bytes
            tmp_file_path: Path to the temporary file containing the font data

        Returns:
            tuple: (embedded_font_object, glyphs_names)
        """
        try:
            if debug:
                print(f"Attempting to load embedded font: {font_file_key}")
                print(f"Font descriptor type: {font_desc.get('/Subtype')}")
                print(f"Font data length: {len(font_data)} bytes")

            # For Type1C fonts (CFF)
            if (
                font_file_key == "/FontFile3"
                and font_desc.get("/Subtype") == "/Type1C"
            ):
                from fontTools.cffLib import CFFFontSet

                try:
                    cff = CFFFontSet()
                    cff.decompile(font_data, None)

                    # Get glyph names from first font in CFF
                    font_name = list(cff.keys())[0]
                    font = cff[font_name]
                    glyphs_names = list(font.CharStrings.keys())
                    if debug:
                        print("CFF font loaded successfully")
                        # Print first 100 glyph names as verification
                        print(f"First 100 glyph names: {glyphs_names[:100]}")
                    return cff, glyphs_names
                except Exception as e:
                    if debug:
                        print(f"Failed to load Type1C/CFF font: {e}")
                    return None, []

            # For Type1 fonts
            elif font_file_key == "/FontFile":
                if debug:
                    print("Type1 font detected, limited support available")
                return None, []

            # For TrueType/OpenType fonts (FontFile2) or other FontFile3 subtypes
            else:
                # First verify if this is actually a TTF/OTF before attempting to load
                is_ttf = False

                try:
                    # Check first 4 bytes for TTF signature
                    with open(tmp_file_path, "rb") as f:
                        signature = f.read(4)
                        if signature in (
                            b"\x00\x01\x00\x00",
                            b"OTTO",
                            b"true",
                            b"typ1",
                        ):
                            is_ttf = True
                            if debug:
                                print(
                                    f"Valid font signature detected: {signature}"
                                )
                        else:
                            if debug:
                                print(
                                    f"Warning: Not a standard TTF/OTF signature: {signature}"
                                )

                    if is_ttf:
                        # Try loading with maximum safety options
                        try:
                            # Use fontNumber=0 to avoid checksum validation
                            # Use lazy=True to delay table loading
                            # print("before")
                            font = TTFont(
                                tmp_file_path,
                                fontNumber=0,
                                # lazy=True,
                                ignoreDecompileErrors=True,
                            )

                            # print("after0")
                            # Try to get glyph names, but this might fail if cmap is corrupt
                            # try:
                            #     glyphs_names = font.getGlyphNames()
                            #     print("after1")
                            # except Exception as e1:

                            # Fallback: try to get glyphs from 'glyf' table directly
                            # if "glyf" in font:
                            #     glyphs_names = list(font["glyf"].glyphs.keys())
                            # else:
                            #     glyphs_names = []
                            glyphs_names = []
                            # print("after2")

                            if debug or True:
                                print(
                                    f"TrueType/OpenType font loaded successfully with {len(glyphs_names)} glyphs"
                                )
                                # Print first 100 glyph names as verification
                                print(
                                    f"First 100 glyph names: {glyphs_names[:100]}"
                                )
                            return font, glyphs_names

                        except Exception as e:
                            if debug:
                                print(
                                    f"Failed to load TrueType/OpenType font with TTFont: {e}"
                                )
                            # Last resort fallback - return empty but don't fail completely
                            return None, []
                    else:
                        if debug:
                            print(
                                "Skipping font loading - not a supported font format"
                            )
                        return None, []
                except Exception as e:
                    if debug:
                        print(f"Failed to load TrueType/OpenType font: {e}")
                        print(f"Font signature check: {is_ttf}")
                    return None, []

        except Exception as e:
            if debug:
                print(f"Exception loading embedded font: {e}")
            import traceback

            traceback.print_exc()
            return None, []
