import pprint
import re
from .pdf_operator import PdfOperator
import string
import os
from .pdf_encoding import PdfEncoding as pnc


class PDFStreamParser:

    def __init__(self):
        self.PRIMATIVE_REGEX = r"<(?P<hex>[0-9a-f]+)>|(?P<name>/\S+)|\((?P<stringO>)(?=\))|(?:\((?P<string>(?:.*?[^\\]))(?=\)))|(?:(?:[^_\-\n\d]|^)(?P<number>[\d.]+))|(?P<numberO>-[\d.]+)"
        self.DICT_CONTENT = r"(?P<key>/\S+)\s+(?P<value><(?:\S+?)>|(?:/\S+)|\((?P<stringO>)(?=\))|(?:\((?:(?:.*?[^\\]))(?=\)))|(?:(?:[^_\-\n\d]|^)(?:[\d.]+))|(?:-[\d.]+))"
        self.TYPES_MAP = {
            "number": float,
            "hex": str,
            "string": str,
            "name": str,
            "binary": str,
        }
        self.TRUNCATED_TOKEN_REGEX = re.compile(
            r"(?:<[^>]*$)",
            re.MULTILINE,
        )
        self.INVALID_ESCAPE = re.compile(
            r"(?:[^\\]|^)\\(?![()\\rntb0-7])", re.MULTILINE | re.DOTALL  # f
        )
        self.ARRAY_REGEX = r"(?:(?P<pre>[^\\\n]|^)\[(?P<array>.*[^\\])?\])"
        self.DICT_REGEX = r"(?P<name>/\w+)?\s*<<(?P<obj>.*?)>>"
        self.SPLIT_REGEX = r"\s+"  # r"(?:\r\n)|\n| |\s"
        self.ID_REGEX = r"ARRAY___\d+|DICT___\d+|NUMBER___\d+|STRING___\d+|NAME___\d+|BINARY___\d+|HEX___\d+"
        self.BOOL_REGEX = r"true|false"
        # self.HAS_HEX_3 = r"(?P<hex>\\(?:\d{3})(?:\\(?:\d{3})|(?:[^\\])))"
        # self.HAS_HEX_3 = ( r"\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:\\)?\D))")
        self.HAS_HEX_3 = re.compile(
            r"(?:\\(?:\d{3})(?:\\(?:\d{3})|(?:(?:\\)?.)))+$", re.MULTILINE
        )
        self.HEX_ITERATE = r"\\(?P<hex>\d{3})|(?P<char>.)"
        self.HEX_ITERATE_V2 = (
            r"\\(?P<hex>\d{3})|(?P<char>.*?(?:(?=\\\d{3})|$))"
        )
        self.HEX_ITERATE_V3 = r"\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:\\)?.(?:(?=\\\d{3})|$)))"
        "\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:.|\\\\)(?:(?=\\\d{3})|$)))"

        self.primatives_counter = 0
        self.arrays_counter = 0
        self.dict_counter = 0
        self.variables_dict = {}
        # self.variables_dict = {}
        # self.prim_
        self.data: str = ""
        self.tokens = []

    def iterate(self):
        if not self.tokens:
            raise ValueError("No tokens to parse")

        arguements = []
        for token in self.tokens:
            if isinstance(token, bool):
                arguements.append(token)
                continue
            elif not token or token == ")":
                continue
            if re.match(self.ID_REGEX, token):
                try:
                    arguements.append(self.variables_dict[token])
                except Exception as e:
                    pprint.pprint(self.variables_dict)
                    raise Exception(e)
            elif token.lstrip(")") in PdfOperator.OPERTORS_SET:
                cmd = token.lstrip(")")
                command = PdfOperator(cmd, arguements)
                arguements = []
                yield command
            else:
                print("----", token)
        self.tokens = []

    # PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "
    #
    # def hex_escape(self, s):
    #     return "".join(
    #         (
    #             c
    #             if c in PDFStreamParser.PRINTABLE
    #             else r"\x{0:02x}".format(ord(c))
    #         )
    #         for c in s
    #     )

    def parse_stream(self, lines: str):
        # lines = lines.replace("\r", "")
        self.variables_dict = {}
        self.arrays_counter = 0
        self.primatives_counter = 0

        lines_list = lines.replace("\\\r", "").split(
            "\n"
        )  # lines.replace("\\\r", "")
        i = 0
        prev_line = ""
        while i < len(lines_list):
            line = lines_list[i]
            if line.strip(" ").endswith("ID") or line.startswith("ID"):
                line1, line2 = line.split("ID", maxsplit=2)
                self.__process_line(line1)
                binary_data = [line2]
                i += 1
                while i < len(lines_list):
                    sub_line = lines_list[i]
                    if sub_line.startswith("EI"):
                        self.primatives_counter += 1
                        name = f"BINARY___{self.primatives_counter}"
                        self.variables_dict[name] = "".join(binary_data)
                        self.tokens.extend([name, "ID", "EI"])
                        self.__process_line(sub_line.lstrip("EI"))
                        break
                    binary_data.append(lines_list[i])
                    i += 1
            elif self.TRUNCATED_TOKEN_REGEX.match(line):
                prev_line += line
                i += 1
                continue
            else:
                self.__process_line(prev_line + line)
            prev_line = ""
            i += 1

        return self

    def __process_line(self, line: str):

        m = re.search(
            PdfOperator.INLINE_IMAGE_OPERATORS_REGEX, line, flags=re.MULTILINE
        )
        if m:
            self.__extract_special_operators(m)
        else:
            self.__extract_variables(line)

    def __extract_special_operators(self, m: re.Match):
        op = m.group("operator")
        values = m.group("value")
        if re.match(self.BOOL_REGEX, values.strip()):
            values = values.strip() == "true"
            self.tokens.append(values)
        else:
            self.__extract_variables(values)
        self.tokens.append(op)

    def __extract_variables(self, line: str):
        self.data = line
        self.data = self.__extrat_dicts()
        self.data = self.__extract_arrays()
        self.data = self.__extract_primatives()

        self.tokens.extend(
            re.split(
                self.SPLIT_REGEX, self.data, flags=re.MULTILINE | re.DOTALL
            )
        )

    def __extract_arrays(self):

        new_string = re.sub(
            self.ARRAY_REGEX,
            lambda m: self.__replace_arrays(m),
            self.data,
            flags=re.MULTILINE | re.DOTALL,
        )
        return new_string

    def __extrat_dicts(self):

        new_string = re.sub(
            self.DICT_REGEX,
            lambda m: self.__replace_dicts(m),
            self.data,
            flags=re.MULTILINE | re.DOTALL,
        )
        return new_string

    def __replace_arrays(self, match):
        self.arrays_counter += 1
        array_id = f"ARRAY___{self.arrays_counter}"

        array = match.group("array")
        pre = match.group("pre")
        if not array:
            self.variables_dict[array_id] = []
            return f"{pre}  {array_id}   "
        parsed_array = []
        self.__extract_primatives(array, parsed_array)
        self.variables_dict[array_id] = parsed_array
        return f"{pre}  {array_id}  "

    def __replace_dicts(self, match):
        self.dict_counter += 1
        dict_id = f"DICT___{self.dict_counter}"
        dict_name = match.group("name") or "UNKOWN"
        dict_str = match.group("obj")
        output_dict = self.__extract_dict_object(dict_str)
        self.variables_dict[dict_id] = output_dict  # {dict_name: output_dict}
        return f" {dict_name} {dict_id} "

    def __extract_dict_object(self, content: str):
        output: dict = {}
        for match in re.finditer(
            self.DICT_CONTENT,
            content,
            flags=re.MULTILINE | re.DOTALL,
        ):
            key = match.group("key")
            value = match.group("value")
            if key and value:
                output[key] = value

        return output

    def __extract_primatives(
        self, data: str | None = None, primatives_array=None
    ):
        if data is None:
            data = self.data
        new_string = re.sub(
            self.PRIMATIVE_REGEX,
            lambda m: self.__replace_primatives(m, primatives_array),
            data,
            flags=re.MULTILINE | re.DOTALL,
        )

        return new_string

    def __replace_hex_in_string(self, match: re.Match):
        # print("hex replace was called")
        int1, int2 = 0, 0
        hex1 = match.groupdict().get("hex1", "").strip("\\")

        hex2 = match.group("hex2")
        char = match.group("char")
        if char:
            if len(char) == 2 and char.startswith("\\"):
                char = char[1:]
            byte_data = pnc.char_to_byte(char)
            byte_string = pnc.byte_to_octal(byte_data)
            # "".join(f"\\{b:03o}" for b in byte_data)
            hex2 = byte_string.lstrip("0o").lstrip("\\")
        final = f"\\{hex1}\\{hex2}"
        return final

    def pdf_hex_to_str(self, hex_text: str) -> str:
        # print("pdf hex was called")
        cleaned = "".join(hex_text.split())
        length = len(cleaned)
        i = 0
        byte_string = ""
        while i < length:
            prefix = ""
            j = i + 4
            if j > length:
                j = length - i
                prefix = "0" * (4 - j)
            try:
                raw_bytes = bytes.fromhex(prefix + cleaned[i:j])
            except Exception as e:
                print(e)
                print(prefix + cleaned[i:j])
                print(hex_text)
                raise Exception(e)
            byte_string += "".join(f"\\{b:03o}" for b in raw_bytes)
            i += 4
        return byte_string

    def __replace_primatives(self, match, primatives_array):
        for p_type, p_value in match.groupdict().items():

            if primatives_array is None:
                self.primatives_counter += 1

            if p_value is None:
                continue

            p_type = p_type.replace("O", "")
            value = self.TYPES_MAP[p_type](p_value)
            if p_type == "hex":
                value = self.pdf_hex_to_str(value)
            if p_type.startswith("string"):
                # if self.INVALID_ESCAPE.match(value):
                #     print("invalid excape char found !!")
                #     print(value)
                value = self.INVALID_ESCAPE.sub(
                    lambda m: m.string.replace("\\", ""), value
                )
                if self.HAS_HEX_3.match(value):
                    value = re.sub(
                        self.HEX_ITERATE_V3,
                        self.__replace_hex_in_string,
                        value,
                        flags=re.DOTALL | re.MULTILINE,
                    )
            primative_id = f"{p_type.upper()}___{self.primatives_counter:06}"
            if primatives_array is not None:
                primatives_array.append(value)
            else:
                self.variables_dict[primative_id] = value

            return f" {primative_id} "
        return " "


if __name__ == "__main__":

    test = r" (\\251 U\( sdf\)CLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)-7( )-27304( )   slkdfj[99304(klsjfj)]cmd   slkdfj[99304(klsjfj)]cmd  slkdfj[99304(klsjfj)]cmd ()cmdempty [(\251 U\( sdf\)CLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)7( )-27304( )333()]TJ "

    parser = PDFStreamParser()
    parser.parse_stream(test.strip())
