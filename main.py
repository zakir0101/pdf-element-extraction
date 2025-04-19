import json
import cairo
from engine.pdf_renderer import BaseRenderer
from engine.pdf_engine import PdfEngine

from fontTools.ttLib import TTFont
from fontTools.unicode import Unicode
from fontTools.agl import AGL2UV, toUnicode  # import AGL2UV
from fontTools.encodings import MacRoman


def main():
    file = "9702_m23_qp_12.pdf"
    file2 = "9709_m23_qp_32.pdf"
    engine: PdfEngine = PdfEngine(f"PDFs\\{file}", scaling=4, debug=True)
    engine.get_page_stream(3).debug_original_stream().execute_stream(200)


def test_cario_matrix_operation():
    print("\nMatrix Operation Tests:")

    # Create initial matrix
    m1 = cairo.Matrix(1, 0, 0, 1, 0, 0)  # Identity matrix
    print("Initial matrix m1:")
    print(f"{m1.xx}    {m1.yx}")
    print(f"{m1.xy}    {m1.yy}")
    print(f"{m1.x0}    {m1.y0}")

    # Test translate
    m1.translate(10, 20)
    print("\nAfter translate (10,20):")
    print(f"{m1.xx}    {m1.yx}")
    print(f"{m1.xy}    {m1.yy}")
    print(f"{m1.x0}    {m1.y0}")

    # Test scale
    m2 = cairo.Matrix(1, 0, 0, 1, 0, 0)
    m2.scale(2, 3)
    print("\nAfter scale (2,3) on m2:")
    print(f"{m2.xx}    {m2.yx}")
    print(f"{m2.xy}    {m2.yy}")
    print(f"{m2.x0}    {m2.y0}")

    # Test transform_point
    x, y = m1.transform_point(5, 5)
    print("\nTransform point (5,5) with translation matrix m1:")
    print(f"Result point: ({x}, {y})")

    x, y = m2.transform_point(5, 5)
    print("\nTransform point (5,5) with scale matrix m2:")
    print(f"Result point: ({x}, {y})")

    # Test transform_distance
    dx, dy = m1.transform_distance(5, 5)
    print("\nTransform distance (5,5) with translation matrix m1:")
    print(f"Result distance: ({dx}, {dy})")

    dx, dy = m2.transform_distance(5, 5)
    print("\nTransform distance (5,5) with scale matrix m2:")
    print(f"Result distance: ({dx}, {dy})")

    # Test matrix multiplication
    m3 = m1.multiply(m2)
    print("\nMatrix multiplication (m1 * m2):")
    print(f"{m3.xx}    {m3.yx}")
    print(f"{m3.xy}    {m3.yy}")
    print(f"{m3.x0}    {m3.y0}")

    # Test associativity of matrix multiplication
    print("\nTesting associativity of matrix multiplication:")
    v = (5, 5)  # Test vector

    # First approach: (v * m1) * m2
    temp_x, temp_y = m1.transform_point(*v)  # v * m1
    result1 = m2.transform_point(temp_x, temp_y)  # (v * m1) * m2
    print("\n(v * m1) * m2 where v is (5,5):")
    print(f"Result: {result1}")

    # Second approach: v * (m1 * m2)
    m3 = m1.multiply(m2)  # m1 * m2
    result2 = m3.transform_point(*v)  # v * (m1 * m2)
    print("\nv * (m1 * m2) where v is (5,5):")
    print(f"Result: {result2}")

    # Compare results
    print("\nResults are equal:", result1 == result2)


def test_image_cairo():
    width, height = 100, 100
    surface = cairo.ImageSurface(cairo.Format.RGB24, width, height)
    data = surface.get_data()
    for y in range(50 - 20, 50 + 20):
        for x in range(50 - 20, 50 + 20):
            index = y * surface.get_stride() + x * 4
            data[index] = 255  # red
            data[index + 1] = 255  # green
            data[index + 2] = 255  # blue
    surface.write_to_png("im.png")


def test_unicode():
    char2 = "Æ"
    char2 = "Á"
    print(ord(char2.encode("ansi")))
    print("\u0420\u043e\u0441\u0441\u0438\u044fdfdfd my name is zakir")
    path = "engine\\agl_list.txt"

    unicode_map = {}
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            if line.startswith("#"):
                continue
            agl_code, unicode = line.split(";")
            unicode_map[agl_code] = unicode.strip()

    for index, (key, value) in enumerate(unicode_map.items()):
        value = json.loads(f'"\\u{value}"')
        print(key, value)
        if index == 10:
            break


def test_ansi_encoding():
    char_ansi_code = "261"
    char_ansi_code = int(char_ansi_code, 8)
    char2 = "Á"
    bytes = bytearray([char_ansi_code])
    print(bytes.decode("ansi"))
    # get the char from the char code
    char = chr(char_ansi_code)
    print(f"char ansi code{char}1")
    print(ord(char2.encode("ansi")))


def test_cairo():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 300)
    ctx = cairo.Context(surface)
    char = "A"
    font_size = 10
    first = None
    for i in range(1, 6):

        ctx.select_font_face(
            "Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL
        )
        curr_size = font_size * i
        ctx.set_font_size(curr_size)
        extent = ctx.text_extents(char)
        width, height = [extent.x_advance, extent.height]
        print("width", width, "height", height)
        if i > 1:
            ratio = width / first[0]
            print("height ratio", ratio, "expected", i)
            print("correction_factor", ratio / i)
        if i == 1:
            first = (width, height)


def test_cairo_renderer():
    engine: PdfEngine = PdfEngine("9702_m23_qp_12.pdf")
    state = engine.state
    renderer = BaseRenderer(state)
    renderer.initialize(800, 600)
    renderer.draw_line(0, 0, 800, 600)
    renderer.save_to_png("output.png")


def text_symbole_encoding():

    num = 179
    char = num.to_bytes().decode("ansi")
    print("char is ", char)
    for i, key in enumerate(AGL2UV.keys()):
        print(key, AGL2UV[key])
        if i == 10:
            break
    keys = [
        ("less"),
        ("greater"),
        ("lessequal"),
        ("solidcircle", 179),
        ("thetaslant", 49),
    ]

    for key in keys:
        value = toUnicode(key[0])
        if value:
            print(key, value)
        else:
            code = key[1]
            # add all possible encodings except utf-*
            encodings = [
                "ansi",
                "mac_roman",
                "cp1252",
                "cp1250",
                "cp1251",
                "cp1253",
                "cp1254",
                "cp1255",
                "cp1256",
                "cp1257",
                "cp1258",
                "cp437",
                "cp850",
                "cp852",
                "cp855",
                "cp866",
                "cp1125",
                "latin_1",
            ]

            encodings.extend(["winansi", "standard", "symbol"])

            encodings.extend(["pdf_doc", "pdf_doc_cp1252"])

            for enc in encodings:
                try:
                    char = code.to_bytes().decode(enc)
                    print("trying encoding :", enc, key, char)
                except:
                    print(enc, "encoding failed")
        AGL2UV.get


if __name__ == "__main__":
    # test_cario_matrix_operation()

    main()
    # test_unicodek

    # test_image_cairo()
