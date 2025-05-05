from pprint import pprint
import re
import math
import string
from .pdf_operator import PdfOperator
from .engine_state import EngineState
import cairo
from cairo import Context, Glyph, ImageSurface
digit_to_name = {
    '0': 'zero',
    '1': 'one',
    '2': 'two',
    '3': 'three',
    '4': 'four',
    '5': 'five',
    '6': 'six',
    '7': 'seven',
    '8': 'eight',
    '9': 'nine',
}
from fontTools.agl import UV2AGL

def char_to_glyph_name(ch):
    codepoint = ord(ch)
    return UV2AGL.get(codepoint, None)

class BaseRenderer:
    def __init__(self, state: EngineState) -> None:
        self.state: EngineState = state
        self.default_char_width = 10
        self.functions_map = {
            "TJ": self.draw_string_array,
            "Tj": self.draw_string,
            "'": self.draw_string,
            '"': self.draw_string,
            "m": self.move_line_to,
            "l": self.draw_line_to,
            "re": self.draw_rectangle,
            "f": self.fill_path,
            "S": self.stroke_path,
            "EI": self.draw_inline_image,
            "W": self.draw_clip,
            "n": self.end_path,
            "q": self.save_state,
            "Q": self.restore_state,
            # "EI": self.test_surface_paint,
            # Existing operators...
            "h": self.close_path,
            "c": self.curve_to,
            "k": self.set_cmyk_color,
            "ET": self.end_text,
        }

        self.surface: ImageSurface | None = None
        self.ctx: Context | None = None

    def initialize(self, width: int, height: int) -> None:
        """Initialize the Cairo surface and context."""
        self.width = width
        self.height = height
        self.surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, self.width, self.height
        )
        # self.surface.set_device_scale(3.0, 3.0)  # Doubles the effective resolution
        self.ctx = cairo.Context(self.surface)
        self.ctx.set_source_rgb(1, 1, 1)  # White
        self.ctx.paint()
        self.ctx.set_source_rgb(0, 0, 0)  # Black
        pass

    def close_path(self, _: PdfOperator):
        """Close the current subpath"""
        self.ctx.close_path()

    def curve_to(self, cmd: PdfOperator):
        """Draw a cubic Bezier curve"""
        x1, y1, x2, y2, x3, y3 = cmd.args
        self.ctx.curve_to(x1, y1, x2, y2, x3, y3)
        self.state.position = [x3, y3]

    def set_cmyk_color(self, cmd: PdfOperator):
        """Set CMYK color"""
        # Color conversion is handled by EngineState
        # Just need to update the context's color
        self.ctx.set_source_rgb(*self.state.fill_color)

    def end_text(self, _: PdfOperator):
        """End text object"""
        # Most of the work is handled by EngineState
        pass

    def draw_clip(self, _: PdfOperator):
        # W operator - Set clipping path
        # Even if we don't fully implement shape rendering,
        # we should at least acknowledge the clipping path
        self.ctx.clip()
        self.ctx.new_path()

    def end_path(self, _: PdfOperator):
        # n operator - End path without filling/stroking
        self.ctx.new_path()

    def save_state(self, _: PdfOperator):
        # q operator
        # handled by EngineState
        self.ctx.save()
        pass

    def restore_state(self, _: PdfOperator):
        # Q operator
        # handled by EngineState
        self.ctx.restore()
        # self.sync_matrix()
        pass

    def get_scale(self, character, width):
        extents = self.ctx.text_extents(character)
        natural_width = extents.x_advance
        ratio = extents.y_advance / natural_width or 1
        h_scale = 1.0 if natural_width == 0 else width / natural_width
        return h_scale, ratio

    def get_glyph_scale(self, gid, width):
        extents = self.ctx.glyph_extents([cairo.Glyph(gid,0,0)])
        natural_width = extents.x_advance
        if natural_width == 0 :
            natural_width = self.default_char_width 
        ratio = extents.y_advance / natural_width or 1 
        h_scale = 1.0 if natural_width == 0 else width / natural_width
        return h_scale, ratio

    def draw_string(self, cmd: PdfOperator):
        # print("drawing single text ", text)
        self.draw_string_array(cmd, is_single=True)

    def draw_string_array(self, cmd: PdfOperator, is_single=False):
        if is_single:
            text_array = [cmd.args[0]]
        else:
            text_array = cmd.args[0]

        state = self.state
        x, y = state.text_position
        font_size = state.font_size
        # am = state.get_current_matrix()
        # self.ctx.set_matrix(am)

        char_regex = r"(?:(?:^|[^\\])\\(?P<symbol>\d{3}))|(?P<char>.)"

        font = self.state.font

        # self.ctx.select_font_face(
        #     font.family,
        #     font.slant,
        #     font.weight,
        # )

        # Check if we have an embedded font face available
        cairo_font_face = None
        # if hasattr(font, "get_cairo_font_face"):
        try:
            cairo_font_face = font.get_cairo_font_face()
            # print("embeded font loaded successfully", cairo_font_face)
        except Exception as e:
            print(f"Error loading embedded font face: {e}")

        # Use the embedded font if available
        if cairo_font_face is not None:
            # print("using embedded font ")
            self.ctx.set_font_face(cairo_font_face)
        else:
            # print(" embeded font NOT found ")
            # Fall back to standard Cairo font selection
            self.ctx.select_font_face(
                font.family,
                font.slant,
                font.weight,
            )

        self.ctx.set_font_size(font_size)

        self.ctx.set_font_size(font_size)

        c_spacing = state.character_spacing
        w_spacing = state.word_spacing

        for element in text_array:
            if isinstance(element, float):
                dx = float(element)
                dx = state.convert_em_to_ts(dx)
                # dx = tm.transform_distance(dx, 0)[0]
                x -= dx
            elif isinstance(element, str):
                element = self.clean_text(element)
                for word in re.split(
                    r"([ ]+)", element, flags=re.DOTALL | re.MULTILINE
                ):
                    if word.isspace():
                        x += w_spacing
                    for char_or in re.finditer(char_regex, word):
                        char_code = None
                        char = char_or.group("char")
                        symbol = char_or.group("symbol")

                        if char:
                            char_width = self.state.font.get_char_width(char)
                            glyph_id  = font.char_to_gid.get(char)
                            if glyph_id is None :
                                if char == "p":
                                    print("correcting p")
                                    char = font.symbol_to_char.get( "pi")
                            #     else:
                            #         raise Exception(f"char {char} not found in font")
                            print("char is ..",char)
                        elif symbol:
                            glyph_id, char_width = font.get_char_code(symbol)
                            char = chr(glyph_id)
                            # char = char_to_glyph_name(symbol)
                            # char_code = font.name_to_gid.get( char )
                            print("symbole is ",symbol)

                        if char_width is None or char_width == 0:
                            print("char width is ", char_width)
                            print("x is ", x)
                            raise ValueError(
                                f"Character {char} not found in font"
                            )
                        char_width = state.convert_em_to_ts(char_width)
                        # h_scale, ratio = self.get_scale(char, char_width)
                        
                        if ord(char) != 0:
                            glyph_id = self.ctx.get_scaled_font().text_to_glyphs(0,0,char,False)[0][0]
                        else:
                            glyph_id = 0
                        h_scale, ratio = self.get_glyph_scale(glyph_id, char_width)
                        self.ctx.save()
                        try:
                            self.ctx.translate(x, 0)
                            self.ctx.scale(h_scale, 1)
                            self.ctx.move_to(0, 0)
                            self.ctx.set_font_size(font_size)
                            # if cairo_font_face :
                            glyph = cairo.Glyph(glyph_id,0,0)
                            # glyph = self.ctx.get_scaled_font().text_to_glyphs(0,0,char,False)[0]
                            self.ctx.show_glyphs([glyph]) 
                            #
                            # else:
                            #     self.ctx.show_text(char)

                        except:
                            print("error")
                            raise ValueError(f"Character {char} not supported")
                            continue

                        self.ctx.restore()
                        x += char_width + c_spacing
            else:
                raise ValueError("Invalid text element")

        if is_single or True:
            pass
            self.state.text_position = [x, y]

    def clean_text(self, text: str):
        text = text.replace("\\(", "(").replace("\\)", ")")
        return text

    def stroke_path(self, _: PdfOperator) -> None:
        """Draw a line using Cairo."""
        if self.ctx is None:
            raise ValueError("Renderer is not initialized")
        self.ctx.set_line_width(self.state.line_width)

        # set gray color
        self.ctx.set_source_rgb(*self.state.stroke_color)
        self.ctx.set_dash(self.state.dash_pattern, 0)
        self.ctx.set_line_cap(self.state.line_cap)
        self.ctx.set_line_join(self.state.line_join)
        self.ctx.set_miter_limit(self.state.miter_limit)
        self.ctx.stroke()
        # self.ctx.stroke_preserve()

    def move_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.move_to(x, y)
        self.state.position = [x, x]

    def draw_line_to(self, cmd: PdfOperator):
        x, y = cmd.args
        self.ctx.line_to(x, y)
        self.state.position = [x, y]

    def draw_rectangle(self, cmd: PdfOperator):
        x, y, width, height = cmd.args
        self.ctx.rectangle(x, y, width, height)

    def fill_path(self, cmd: PdfOperator) -> None:
        """Fill the current path using Cairo."""
        fill_rule = cairo.FILL_RULE_WINDING
        self.ctx.set_fill_rule(fill_rule)
        self.ctx.set_source_rgb(*self.state.fill_color)
        self.ctx.fill()

    PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "

    def hex_escape(self, s):
        return "".join(
            c if c in BaseRenderer.PRINTABLE else r"\x{0:02x}".format(ord(c))
            for c in s
        )

    def draw_inline_image(self, cmd: PdfOperator):
        data = self.state.inline_image_data
        width = self.state.inline_image_width
        height = self.state.inline_image_height
        bits_per_component = self.state.inline_image_bits_per_component
        is_mask = self.state.inline_image_mask

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        surface_data = surface.get_data()
        stride = surface.get_stride()

        if is_mask and bits_per_component == 1:
            fill_color = self.state.fill_color
            r, g, b = [int(c * 255) for c in fill_color]

            for y in range(height):
                for x in range(width):
                    byte_index = (y * width + x) // 8
                    bit_index = 7 - ((y * width + x) % 8)

                    if byte_index < len(data):
                        bit_value = (data[byte_index] >> bit_index) & 1
                        idx = y * stride + x * 4

                        if bit_value == 0:  # Black pixel
                            surface_data[idx] = b  # Blue
                            surface_data[idx + 1] = g  # Green
                            surface_data[idx + 2] = r  # Red
                            surface_data[idx + 3] = 255  # Alpha
                        else:
                            surface_data[idx] = 0  # Blue
                            surface_data[idx + 1] = 0  # Green
                            surface_data[idx + 2] = 0  # Red
                            surface_data[idx + 3] = 0  # Alpha (transparent)
        else:
            # Handle regular image case
            bytes_per_pixel = bits_per_component // 8
            if bytes_per_pixel == 0:
                bytes_per_pixel = 1

            for y in range(height):
                for x in range(width):
                    idx_out = y * stride + x * 4
                    idx_in = (y * width + x) * bytes_per_pixel

                    if idx_in + bytes_per_pixel <= len(data):
                        # Read pixel value based on bits_per_component
                        if bits_per_component <= 8:
                            pixel = data[idx_in]
                            pixel = (pixel * 255) // (
                                (1 << bits_per_component) - 1
                            )
                            # Grayscale
                            surface_data[idx_out] = pixel  # Blue
                            surface_data[idx_out + 1] = pixel  # Green
                            surface_data[idx_out + 2] = pixel  # Red
                            surface_data[idx_out + 3] = 255  # Alpha
                        else:
                            # RGB data
                            r = data[idx_in]
                            g = (
                                data[idx_in + 1]
                                if idx_in + 1 < len(data)
                                else 0
                            )
                            b = (
                                data[idx_in + 2]
                                if idx_in + 2 < len(data)
                                else 0
                            )
                            surface_data[idx_out] = b  # Blue
                            surface_data[idx_out + 1] = g  # Green
                            surface_data[idx_out + 2] = r  # Red
                            surface_data[idx_out + 3] = 255  # Alpha
        surface.mark_dirty()

        x, y = self.state.position

        self.ctx.save()
        self.ctx.translate(x, y)
        self.ctx.set_source_surface(surface, 0, 0)
        source = self.ctx.get_source()
        source.set_filter(cairo.FILTER_FAST)

        # Other options:
        # cairo.FILTER_FAST - A high-performance filter
        # cairo.FILTER_GOOD - A reasonable-quality filter
        # cairo.FILTER_BEST - The highest-quality filter
        # cairo.FILTER_NEAREST - Nearest-neighbor filter
        # cairo.FILTER_BILINEAR - Linear interpolation in two dimensions
        # cairo.FILTER_GAUSSIAN - Gaussian convolution filter

        self.ctx.paint()
        self.ctx.restore()
        surface.finish()

    def sync_matrix(self):
        """Sync Cairo's CTM with the current PDF state matrix"""
        current_matrix = self.state.get_current_matrix()
        # self.ctx.identity_matrix()
        self.ctx.set_matrix(current_matrix)

    def execute_command(self, cmd: PdfOperator):

        if cmd.name in self.state.do_sync_after:
            # print("syncing matrix, after ", cmd.name)
            self.sync_matrix()
        func = self.functions_map.get(cmd.name)
        if func:
            func(cmd)

    def save_to_png(self, filename: str) -> None:
        """Save the rendered content to a PNG file."""
        print("saving image")
        if self.surface is None:
            raise ValueError("Renderer is not initialized")
        self.surface.write_to_png(filename)

    # regex = r"(?:^|[^\\])\\(?P<symbol>\d{3})"

    # text = re.sub(regex ,
    #               lambda m : self.state.font.get_unicode(m.group("symbol")),
    #               text,flags = re.MULTILINE | re.DOTALL)

    # def test_surface_paint(self):
    #     """
    #     Test function to paint a simple black box in the middle of the screen
    #     using the same surface painting method as draw_inline_image
    #     """
    #     # Create a small test surface (50x50 pixels)
    #     width, height = 50, 50
    #     surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    #
    #     print("Main surface dimensions:", self.width, self.height)
    #     print("Test surface dimensions:", width, height)
    #
    #     surface_data = surface.get_data()
    #     temp = surface_data.tolist()
    #     print("Initial surface data:", temp[:20])
    #
    #     stride = surface.get_stride()
    #     for y in range(height):
    #         for x in range(width):
    #             idx = y * stride + x * 4
    #             surface_data[idx] = 0  # Blue
    #             surface_data[idx + 1] = 0  # Green
    #             surface_data[idx + 2] = 0  # Red
    #             surface_data[idx + 3] = 255  # Alpha
    #
    #     surface.mark_dirty()
    #     temp = surface_data.tolist()
    #     print("After filling surface data:", temp[:20])
    #
    #     # Position in middle of screen
    #     x = (self.width - width) / 2
    #     y = (self.height - height) / 2
    #     print("Positioning at:", x, y)
    #
    #     # Create pattern from surface
    #     self.ctx.save()
    #     self.ctx.identity_matrix()
    #     self.ctx.set_source_surface(surface, x, y)
    #     self.ctx.paint()
    #     self.ctx.restore()
    #     surface.finish()
