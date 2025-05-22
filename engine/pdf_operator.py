class PdfOperator:

    NEED_SCALING = 0x01
    NEED_TRANSLATION = 0x02

    def __init__(self, op_name, arguements: list):
        self.name = op_name
        self.args = arguements

        args_string = list(map(str, arguements))
        context = {f"operands{i}": str(op) for i, op in enumerate(arguements)}
        context["operands"] = ", ".join(args_string)
        explaination = self.OPERATORS.get(op_name)
        # if explaination:  # print(context)
        try:
            # print(explaination)
            self.explaination = explaination % context
        except Exception as e:
            print("ERROR: while parsing operator")
            print(op_name, arguements, "\n\n")
            raise ValueError(e)

    def get_explanation(self, *args):

        args_string = list(map(str, args))
        context = {f"operands{i}": str(op) for i, op in enumerate(args)}
        context["operands"] = ", ".join(args_string)
        explaination = PdfOperator.OPERATORS.get(self.name)
        if explaination:
            return explaination % context

        return "Operator not found"

    def __str__(self):
        return f"{self.name} // {self.explaination}"

    def get_modification_flags(self):
        flag = 0
        if self.name in {
            "Ts",
            "TL",
            "Tz",
            "Tw",
            "Tc",
            '"',
            "'",
            "T*",
            "TD",
            "Td",
        }:
            flag |= PdfOperator.NEED_SCALING
        if self.name in {"TD", "Td", "T*", "'", "''"}:
            flag |= PdfOperator.NEED_TRANSLATION

        return flag

    @staticmethod
    def is_operator_valid(operator_name):
        return operator_name in PdfOperator.OPERTORS_SET

    @staticmethod
    def get_graphics_operator():
        return {
            # --------------------------------------------------
            # Graphics State Operators (Chapter 4/5 in full spec)
            # --------------------------------------------------
            "q": "Save current graphics state (no parameters)",
            "Q": "Restore most recent graphics state from stack (no parameters)",
            "cm": (
                "Concatenate CTM matrix [a=%(operands0)s, b=%(operands1)s, c=%(operands2)s, "
                "d=%(operands3)s, e=%(operands4)s, f=%(operands5)s] (6 numbers)"
            ),
            "gs": "Set graphics state [dict=%(operands)s]",
            "d": (
                "Set dash pattern [dash_array=%(operands0)s, phase=%(operands1)s] "
                "(empty array = solid line; phase=offset)"
            ),
            "i": "Set flatness tolerance [flatness=%(operands)s] (0-100, 0=device default)",
            "j": "Set line join style [mode=%(operands)s] (0=miter, 1=round, 2=bevel)",
            "J": "Set line cap style [mode=%(operands)s] (0=butt, 1=round, 2=square)",
            "M": "Set miter limit [limit=%(operands)s] (≥1, default=10)",
            "w": "Set line width [width=%(operands)s] (default=1)",
            "/SMask": "EXG: set soft mask !!! [operands=%(operands)s]",
            "/BM": "EXG: set blend mode !!! [operands=%(operands)s]",
            "/OP": "EXG: !!! [operands=%(operands)s]",
            "/op": "EXG: set overprint stroke !!! [operands=%(operands)s]",
            "/OPM": "EXG: set overprint fill !!! [operands=%(operands)s]",
            "/SA": "EXG: set stroke adjustments !!! [operands=%(operands)s]",
            "/Font": "EXG: set font !!! [operands=%(operands)s]",
            "/OPM": "EXG: set overprint mode !!! [operands=%(operands)s]",
            "/CA": "EXG: set stroke alpha !!! [operands=%(operands)s]",
            "/ca": "EXG: set fill apha !!! [operands=%(operands)s]",
            "/LW": "EXG: set line width !!! [operands=%(operands)s]",
            "/LC": "EXG: set line cap !!! [operands=%(operands)s]",
            "/LJ": "EXG: set line Join !!! [operands=%(operands)s]",
            "/ML": "EXG: set meter limit !!! [operands=%(operands)s]",
            "/D": "EXG: set dash pattern !!! [operands=%(operands)s]",
            "Tr": "set rending mode !!! [operands=%(operands)s]",
            "EX": "Unkown operators !! [operands=%(operands)s]",
            "BX": "Unkown operatkor !!! [operands=%(operands)s]",
            "sh": "Not Implemented operatkor !!! [operands=%(operands)s]",
            "d0": "set glyph width in type3 font [operands=%(operands)s]",
            "d1": "set glyph width in type3 font [operands=%(operands)s]",
        }

    GRAPHICS_OPERATORS = get_graphics_operator()
    GRAPHICS_OPERATORS_SET = set(GRAPHICS_OPERATORS.keys())

    @staticmethod
    def get_inline_image_operators():
        return {
            # --------------------------------------------------
            # Inline Image Operators (Section 4.8)
            # --------------------------------------------------
            "BI": "Begin inline image (no parameters)",
            "ID": "Begin image data (raw bytes follow)",
            "EI": "End inline image (no parameters)",
            "/W": "Set image width [width=%(operands)s] (positive integer)",
            "/H": "Set image height [height=%(operands)s] (positive integer)",
            "/IM": "Set image interpolation [interp=%(operands)s] (true or false)",
            "/BPC": "Set bits per component [bpc=%(operands)s] (1, 2, 4, 8, 16, 32)",
            "/CS": "Set color space [colorSpace=%(operands)s] (name or array)",
            "/F": "Set filter [filter=%(operands)s] (name or array)",
            "/D": "D=Decode, Unkown operator  [filter=%(operands)s]",
            "/DP": " Unkown operator  [filter=%(operands)s]",
        }

    INLINE_IMAGE_OPERATORS = get_inline_image_operators()
    INLINE_IMAGE_OPERATORS_SET = set(INLINE_IMAGE_OPERATORS.keys())
    INLINE_IMAGE_OPERATORS_REGEX = r"^(?P<operator>\/(?:W|H|IM|BPC|CS))\s+(?P<value>\d+|true|false|\[.*?\])$"

    @staticmethod
    def get_text_operators():
        return {
            # --------------------------------------------------
            # Text Operators (from previous answer, kept for completeness)
            # --------------------------------------------------
            "BT": "Begin text object (no parameters)",
            "ET": "End text object (no parameters)",
            # Text State Operators
            "Tc": "Set character spacing [charSpace=%(operands)s] (text space units)",
            "Tf": "Set text font [font=%(operands0)s] and size [size=%(operands1)s] (points)",
            "TL": "Set text leading [leading=%(operands)s] (text space units)",
            "Tr": "Set text rendering mode [mode=%(operands)s] (0=fill, 1=stroke, etc)",
            "Ts": "Set text rise [rise=%(operands)s] (for sub/superscripts)",
            "Tw": "Set word spacing [wordSpace=%(operands)s] (text space units)",
            "Tz": "Set horizontal scaling [scale=%(operands)s%%] (percentage)",
            # Text Positioning Operators
            "Td": "Move text position [tx=%(operands0)s, ty=%(operands1)s] (text space units)",
            "TD": "Move text position & set leading [tx=%(operands0)s, ty=%(operands1)s] (sets leading=-ty)",
            "Tm": (
                "Set text matrix [a=%(operands0)s b=%(operands1)s c=%(operands2)s "
                "d=%(operands3)s e=%(operands4)s f=%(operands5)s] (affects scaling/positioning)"
            ),
            "T*": "Move to next text line (uses current leading)",
            # Text String Operators
            "Tj": "Show text [string=%(operands)s]",
            "'": "Move to next line and show text [string=%(operands)s]",
            '"': (
                "Move to next line with [aw=%(operands0)s, ac=%(operands1)s] and show text "
                "[string=%(operands2)s] (additional spacing)"
            ),
            "TJ": "Show text array with kerning [elements=%(operands)s] (numbers=position adjustments)",
            # XObject/Image Operators
            "Do": "Draw XObject [name=%(operands)s] (image/form)",
            # "BI": "Begin inline image (header parameters follow)",
            # "ID": "Begin image data (raw bytes follow)",
            # "EI": "End inline image (no parameters)",
            # Marked Content
            "EMC": "End marked content sequence (no parameters)",
            "BDC": "set marked Content [Content=%(operands)s]",
        }

    TEXT_OPERATORS = get_text_operators()
    TEXT_OPERATORS_SET = set(TEXT_OPERATORS.keys())

    @staticmethod
    def get_color_operators():
        return {
            # --------------------------------------------------
            # Color Operators (Section 7.4)
            # --------------------------------------------------
            "g": "Set fill color to grayscale [gray=%(operands)s] (0=black, 1=white)",
            "G": "Set stroke color to grayscale [gray=%(operands)s] (0=black, 1=white)",
            "k": (
                "Set fill color to CMYK [cyan=%(operands0)s, magenta=%(operands1)s, "
                "yellow=%(operands2)s, black=%(operands3)s] (0-1 per component)"
            ),
            "K": (
                "Set stroke color to CMYK [cyan=%(operands0)s, magenta=%(operands1)s, "
                "yellow=%(operands2)s, black=%(operands3)s] (0-1 per component)"
            ),
            "rg": (
                "Set fill color to RGB [red=%(operands0)s, green=%(operands1)s, "
                "blue=%(operands2)s] (0-1 per component)"
            ),
            "RG": (
                "Set stroke color to RGB [red=%(operands0)s, green=%(operands1)s, "
                "blue=%(operands2)s] (0-1 per component)"
            ),
            # ← new entries below →
            # TODO: implement logic for the following operators ! ( if needed )
            "cs": "Set fill color space to             [colorspace=%(operands0)s]",
            "CS": "Set fill color space to             [colorspace=%(operands0)s]",
            "sc": "Set fill color in current space      [components=%(operands)s]",
            "SC": "Set fill color in current space      [components=%(operands)s]",
            "scn": "Set fill color or pattern/shading   [components=%(operands)s]",
            "SCN": "Set fill color or pattern/shading   [components=%(operands)s]",
        }

    COLOR_OPERATORS = get_color_operators()
    COLOR_OPERATORS_SET = set(COLOR_OPERATORS.keys())

    @staticmethod
    def get_path_operators():
        return {
            # --------------------------------------------------
            # Path Segment Operators (Section 7.5.1)
            # --------------------------------------------------
            "m": "Move current point to [x=%(operands0)s, y=%(operands1)s] (no line drawn)",
            "l": "Draw line to [x=%(operands0)s, y=%(operands1)s] (sets new current point)",
            "c": (
                "Draw cubic Bézier curve with control points [x1=%(operands0)s, y1=%(operands1)s, "
                "x2=%(operands2)s, y2=%(operands3)s] to endpoint [x3=%(operands4)s, y3=%(operands5)s]"
            ),
            "v": (
                "Draw Bézier curve with implicit first control point (current point) and "
                "second control point [x2=%(operands0)s, y2=%(operands1)s], ending at [x3=%(operands2)s, y3=%(operands3)s]"
            ),
            "y": (
                "Draw Bézier curve with first control point [x1=%(operands0)s, y1=%(operands1)s] "
                "and implicit second control point (endpoint), ending at [x3=%(operands2)s, y3=%(operands3)s]"
            ),
            "re": (
                "Add rectangle to path [x=%(operands0)s, y=%(operands1)s, "
                "width=%(operands2)s, height=%(operands3)s]"
            ),
            "h": "Close current subpath (draw line to starting point)",
            # --------------------------------------------------
            # Path Painting Operators (Section 7.5.2)
            # --------------------------------------------------
            "n": "End path without stroking/filling (no parameters)",
            "S": "Stroke the path (no parameters)",
            "s": "Close path and stroke (no parameters)",
            "f": "Fill path using non-zero winding rule (no parameters)",
            "f*": "Fill path using even-odd rule (no parameters)",
            "B": "Fill and stroke path (no parameters)",
            "b": "Close path, fill, and stroke (no parameters)",
            "B*": "Fill (even-odd) and stroke path (no parameters)",
            "b*": "Close path, fill (even-odd), and stroke (no parameters)",
            # --------------------------------------------------
            # Clipping Operators (Section 7.5.3)
            # --------------------------------------------------
            "W": "Set clipping path using non-zero winding rule (no parameters)",
            "W*": "Set clipping path using even-odd rule (no parameters)",
        }

    PATH_OPERATORS = get_path_operators()
    PATH_OPERATORS_SET = set(PATH_OPERATORS.keys())

    OPERATORS = (
        GRAPHICS_OPERATORS
        | TEXT_OPERATORS
        | COLOR_OPERATORS
        | PATH_OPERATORS
        | INLINE_IMAGE_OPERATORS
    )
    OPERTORS_SET = (
        GRAPHICS_OPERATORS_SET
        | TEXT_OPERATORS_SET
        | COLOR_OPERATORS_SET
        | PATH_OPERATORS_SET
        | INLINE_IMAGE_OPERATORS_SET
    )
