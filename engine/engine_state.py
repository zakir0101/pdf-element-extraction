import cairo
import string

from .pdf_operator import PdfOperator
from .pdf_font import PdfFont
from PyPDF2.filters import (
    ASCII85Decode,
    ASCIIHexDecode,
    LZWDecode,
    DCTDecode,
    decompress,
)
from cairo import Matrix
import copy


class EngineState:

    def __init__(
        self,
        font_map: dict[str, PdfFont],
        scale: int,
        screen_height: int = 0,
        debug: bool = False,
    ):
        self.debug = debug
        self.scale = scale
        self.screen_height = screen_height * scale
        CTM = [scale, 0.0, 0.0, scale, 0.0, 0.0]
        text_matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        self.cm_matrix = Matrix(*CTM)
        self.tm_matrix = Matrix(*text_matrix)
        self.text_position = [0.0, 0.0]
        self.in_text_block = False
        self.character_spacing = 0.0
        self.word_spacing = 0.0
        # self.horizontal_scaling = 100.0
        self.leading = 0.0

        for font in font_map.values():
            self.font: PdfFont = font
            break
        self.font_size = 0
        # self.text_rize = 0.0
        self.font_map = font_map

        self.line_width: float = 1.0
        self.position = [0.0, 0.0]
        self.dash_pattern = []
        self.stroke_color = [0.0, 0.0, 0.0]
        self.fill_color = [1.0, 1.0, 1.0]
        self.line_cap = cairo.LINE_CAP_BUTT
        self.line_join = cairo.LINE_JOIN_MITER
        self.miter_limit = 10.0
        self.state_stack: list[dict] = []
        self.functions_map = {
            "q": self.save_state,
            "Q": self.restore_state,
            "BT": self.begin_text,
            "ET": self.end_text,
            "cm": self.set_ctm,
            "Tm": self.set_text_matrix,
            "Td": self.set_text_position,
            "TD": self.set_text_position_and_leading,
            "T*": self.move_with_leading,
            "TJ": self.clear_text_position_after_tj,
            "'": self.move_with_leading,
            '"': self.move_with_leading_and_spacing,
            "Tc": self.set_character_spacing,
            "Tw": self.set_word_spacing,
            "Tz": self.set_horizontal_scaling,
            "TL": self.set_leading,
            "Tf": self.set_font,
            "Ts": self.set_text_rize,
            # graphics state operators
            "w": self.set_line_width,
            "d": self.set_dash_pattern,
            "G": self.set_stroke_color_gray,
            "g": self.set_fill_color_gray,
            "J": self.set_line_cap,
            "j": self.set_line_join,
            "M": self.set_meter_limit,
            # "m" : self.move_position,
            # "l" : self.draw_line_to
            # "S" : self.stroke_path,
            # inline image operators
            "BI": self.begin_inline_image,
            "/W": self.set_inline_image_width,
            "/H": self.set_inline_image_height,
            "/BPC": self.set_inline_image_bits_per_component,
            # "/CS" : self.set_inline_image_color_space,
            "/F": self.set_inline_image_filter,
            "/IM": self.set_inline_image_mask,
            "ID": self.decode_inline_image,
            "EI": lambda _: None,
            # Path Construction
            "h": self.close_path,
            "c": self.curve_to,
            # Color Operators
            "k": self.set_cmyk_color,
        }

        self.do_sync_after = [
            "Tm",
            "cm",
            "BT",
            "ET",
            # "q",
            "Td",
            "TD",
            "T*",
            "'",
            '"',
            "Tz",
            "Ts",
        ]

        self.inline_image_width = 0
        self.inline_image_height = 0
        self.inline_image_bits_per_component = 0
        self.inline_image_mask = False
        self.inline_image_filter = []
        self.inline_image_data: bytes = b""

    INLINE_DECODER_MAP = {
        "/LZW": "decode_lzw",
        "/RL": "decode_run_length",
        "/DCT": "decode_dct",
        "/A85": "decode_ascii85",
        "/AHx": "decode_ascii_hex",
    }

    PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "

    def begin_text(self, _: PdfOperator):

        self.in_text_block = True
        self.tm_matrix = Matrix(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def end_text(self, _: PdfOperator):
        self.in_text_block = False

    def get_current_matrix(
        self,
    ):
        """Get the appropriate transformation matrix based on context"""

        cc0 = cairo.Matrix(1, 0, 0, -1, 0, self.screen_height)
        cm = self.cm_matrix
        if self.in_text_block:
            tm = self.tm_matrix

            cc1 = cairo.Matrix(1, 0, 0, -1, 0, 0)
            return cc1.multiply(tm.multiply(cm.multiply(cc0)))
        else:

            cc1 = cairo.Matrix(1, 0, 0, 1, 0, 0)
            return cc1.multiply(cm.multiply(cc0))

    def close_path(self, _: PdfOperator):
        """h operator - Close the current subpath"""
        # This will be handled by the renderer
        pass

    def curve_to(self, cmd: PdfOperator):
        """c operator - Cubic Bezier curve"""
        x1, y1, x2, y2, x3, y3 = cmd.args
        # Store control points and endpoint for renderer
        self.position = [x3, y3]
        if self.debug:
            return [x1, y1, x2, y2, x3, y3]

    def set_cmyk_color(self, cmd: PdfOperator):
        """k operator - Set CMYK color for filling"""
        c, m, y, k = cmd.args
        # Convert CMYK to RGB (simplified conversion)
        r = (1 - c) * (1 - k)
        g = (1 - m) * (1 - k)
        b = (1 - y) * (1 - k)
        self.fill_color = [r, g, b]
        if self.debug:
            return [c, m, y, k]

    def decode_lzw(self, data: bytes):
        return LZWDecode.decode(data)

    def decode_run_length(self, data: bytes):
        return decompress(data)

    def decode_dct(self, data: bytes):
        return DCTDecode.decode(data)

    def decode_ascii85(self, data: bytes):
        return ASCII85Decode.decode(data)

    def decode_ascii_hex(self, data: bytes):
        decoded_str = ASCIIHexDecode.decode(data.decode("ascii"))
        return decoded_str.encode("ascii")

    def hex_escape(self, s):
        return "".join(
            (c if c in EngineState.PRINTABLE else r"\x{0:02x}".format(ord(c)))
            for c in s
        )

    def decode_inline_image(self, operator: PdfOperator):
        if len(operator.args) == 0:
            raise ValueError("No image data found in inline image")
        data = operator.args[0]
        # Convert string data to bytes if needed
        if isinstance(data, str):
            data = data.encode("utf-8")

        # Apply each filter in sequence
        decoded_data = data
        for filter_name in self.inline_image_filter:
            decoder_method_name = self.INLINE_DECODER_MAP.get(filter_name)
            if decoder_method_name:
                # Get the actual method and decode
                decoder = getattr(self, decoder_method_name)
                decoded_data = decoder(decoded_data)
        self.inline_image_data = decoded_data
        return None

    def begin_inline_image(self, _: PdfOperator):
        self.inline_image_width = 0
        self.inline_image_height = 0
        self.inline_image_bits_per_component = 0
        self.inline_image_mask = False
        return None

    def set_inline_image_width(self, command: PdfOperator):
        self.inline_image_width = int(command.args[0])
        return None

    def set_inline_image_height(self, command: PdfOperator):
        self.inline_image_height = int(command.args[0])
        return None

    def set_inline_image_bits_per_component(self, command: PdfOperator):
        bpc = int(command.args[0])
        self.inline_image_bits_per_component = bpc
        return None

    def set_inline_image_mask(self, command: PdfOperator):
        self.inline_image_mask = bool(command.args[0])
        return None

    def set_inline_image_filter(self, command: PdfOperator):
        filter = command.args[0]
        if isinstance(filter, str):
            filter = [filter]
        self.inline_image_filter = filter
        return None

    def dump_dict(self):
        m1 = self.cm_matrix
        m2 = self.tm_matrix
        return {
            # "CTM": copy.copy(self.CTM),
            # "text_matrix": copy.copy(self.text_matrix),
            "cm_matrix": copy.copy([m1.xx, m1.yx, m1.xy, m1.yy, m1.x0, m1.y0]),
            "tm_matrix": copy.copy([m2.xx, m2.yx, m2.xy, m2.yy, m2.x0, m2.y0]),
            "text_position": copy.copy(self.text_position),
            "character_spacing": copy.copy(self.character_spacing),
            "word_spacing": copy.copy(self.word_spacing),
            # "horizontal_scaling": copy.copy(self.horizontal_scaling),
            "leading": copy.copy(self.leading),
            "font_name": copy.copy(self.font),
            "font_size": copy.copy(self.font_size),
            # "text_rize": copy.copy(self.text_rize),
            "line_width": copy.copy(self.line_width),
            "position": copy.copy(self.position),
            "dash_pattern": copy.copy(self.dash_pattern),
            "stroke_color": copy.copy(self.stroke_color),
            "fill_color": copy.copy(self.fill_color),
            "miter_limit": copy.copy(self.miter_limit),
            "line_cap": copy.copy(self.line_cap),
            "line_join": copy.copy(self.line_join),
            # inline image
            "inline_image_width": copy.copy(self.inline_image_width),
            "inline_image_height": copy.copy(self.inline_image_height),
            "inline_image_bits_per_component": copy.copy(
                self.inline_image_bits_per_component
            ),
            "inline_image_mask": copy.copy(self.inline_image_mask),
        }

    def save_state(self, _: PdfOperator):
        self.state_stack.append(self.dump_dict())
        return None

    def restore_state(self, _: PdfOperator):
        if len(self.state_stack) == 0:
            return None
        state = self.state_stack.pop()
        for key, value in state.items():
            if key == "cm_matrix" or key == "tm_matrix":
                setattr(self, key, Matrix(*value))
            else:
                setattr(self, key, value)
        return None

    def set_line_width(self, command: PdfOperator):
        self.line_width = float(command.args[0])
        if self.debug:
            cm = self.cm_matrix
            return [cm.transform_distance(self.line_width, 0)[0]]

    def set_stroke_color_gray(self, command: PdfOperator):
        grayscale = float(command.args[0]) * 255
        self.stroke_color = [grayscale, grayscale, grayscale]
        if self.debug:
            return None

    def set_fill_color_gray(self, command: PdfOperator):
        grayscale = float(command.args[0])
        # print("fill color = ", grayscale)
        self.fill_color = [grayscale, grayscale, grayscale]
        if self.debug:
            return None

    def set_dash_pattern(self, command: PdfOperator):
        self.dash_pattern = command.args[0]
        if self.debug:
            return None

    def set_line_cap(self, command: PdfOperator):
        value = int(command.args[0])
        if value == 0:
            self.line_cap = cairo.LINE_CAP_BUTT
        elif value == 1:
            self.line_cap = cairo.LINE_CAP_ROUND
        elif value == 2:
            self.line_cap = cairo.LINE_CAP_SQUARE

        if self.debug:
            return None

    def set_line_join(self, command: PdfOperator):
        value = int(command.args[0])
        if value == 0:
            self.line_join = cairo.LINE_JOIN_MITER
        elif value == 1:
            self.line_join = cairo.LINE_JOIN_ROUND
        elif value == 2:
            self.line_join = cairo.LINE_JOIN_BEVEL

        if self.debug:
            return None

    def set_meter_limit(self, command: PdfOperator):
        self.miter_limit = float(command.args[0])
        if self.debug:
            return None

    def set_font(self, command: PdfOperator):
        # print(command.args)
        fontname, font_size = command.args
        self.font = self.font_map[fontname]
        self.font_size = float(font_size)

        if self.debug:
            return None

    # def get_line_width(self):
    #     return self.cm_matrix.transform_distance(self.line_width, 0)[0]

    # ========================================
    # ============ NEED REVISION =============
    # ============== BELOW  ==================

    def set_ctm(self, command: PdfOperator):
        """
        Modifies the CTM by concatenating the specified matrix. Although the operands
        specify a matrix, they are passed as six numbers, not an array
        multiply old ctm with new one
        """
        new_ctm_matrix = Matrix(*command.args)
        self.cm_matrix = new_ctm_matrix.multiply(self.cm_matrix)
        if self.debug:
            return [*self.cm_matrix]
        return None

    def set_text_matrix(self, command: PdfOperator):
        if not self.in_text_block:
            return  # Ignore text matrix operations outside text blocks
        self.tm_matrix = Matrix(*command.args)
        self.text_position = [0.0, 0.0]
        if self.debug:
            return [*self.tm_matrix]

    def set_text_position(self, command: PdfOperator):
        """
        set position offset from text-space origin
        """
        x, y = [*command.args]
        self.tm_matrix.translate(x, y)
        self.text_position = [0.0, 0.0]
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return m.transform_distance(x, y)

    def set_leading(self, command: PdfOperator):
        self.leading = float(command.args[0])
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return [m.transform_distance(0, self.leading)[1]]

    def set_text_position_and_leading(self, command: PdfOperator):
        x, y = [*command.args]
        self.leading = -float(y)
        self.tm_matrix.translate(x, y)
        self.text_position = [0.0, 0.0]
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return m.transform_distance(x, y)

    def move_with_leading(self, _: PdfOperator):
        self.tm_matrix.translate(0, -self.leading)
        if self.debug:
            return None

    def move_with_leading_and_spacing(self, command: PdfOperator):
        sw, sc = command.args
        self.character_spacing = float(sc)
        self.word_spacing = float(sw)
        self.tm_matrix.translate(0, self.leading)
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return [
                m.transform_distance(sw, 0)[0],
                m.transform_distance(sc, 0)[0],
            ]

    def set_character_spacing(self, command: PdfOperator):
        self.character_spacing = float(command.args[0])
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return [m.transform_distance(self.character_spacing, 0)[0]]

    def set_word_spacing(self, command: PdfOperator):
        self.word_spacing = float(command.args[0])
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return [m.transform_distance(self.word_spacing, 0)[0]]

    def set_horizontal_scaling(self, command: PdfOperator):
        horizontal_scaling = command.args[0]
        self.tm_matrix.scale(horizontal_scaling / 100.0, 1)
        if self.debug:
            return None

    def clear_text_position_after_tj(self, _: PdfOperator):
        self.text_position = [0, 0]

    def set_text_rize(self, command: PdfOperator):
        self.tm_matrix.translate(0, self.text_rize)
        if self.debug:
            m = self.tm_matrix.multiply(self.cm_matrix)
            return [m.transform_distance(0, self.text_rize)[0]]

    def convert_em_to_ts(self, em: float):
        return em / 1000 * self.font_size

    def execute_command(self, command: PdfOperator):
        func = self.functions_map.get(command.name)
        if func:
            args_scaled = func(command)
            if args_scaled is not None:
                return command.get_explanation(*args_scaled)

        return ""

    # def convert_ts_to_us(self, x, y, is_translation=True):
    #     """
    #     convert text-space to user space
    #     """
    #     return (
    #         self.tm_matrix.transform_point(x, y)
    #         if is_translation
    #         else self.tm_matrix.transform_distance(x, y)
    #     )
    #
    # def convert_us_to_ds(self, x, y, is_translation=True):
    #     """
    #     convert user-space to device space
    #     """
    #     return (
    #         self.cm_matrix.transform_point(x, y)
    #         if is_translation
    #         else self.cm_matrix.transform_distance(x, y)
    #     )
    #
    # def convert_ts_to_ds(self, x, y, is_translation=True):
    #     """
    #     convert text-space to device-space
    #     """
    #     am = self.tm_matrix.multiply(self.cm_matrix)
    #
    #     return (
    #         am.transform_point(x, y)
    #         if is_translation
    #         else am.transform_distance(x, y)
    #     )
