import re
from .pdf_operator import PdfOperator
import string


class PDFStreamParser:

    def __init__(self):
        self.PRIMATIVE_REGEX = r"<(?P<hex>\S+?)>|(?P<name>/\S+)|\((?P<stringO>)(?=\))|(?:\((?P<string>(?:.*?[^\\]))(?=\)))|(?:(?:[^_\-\n\d]|^)(?P<number>[\d.]+))|(?P<numberO>-[\d.]+)"
        self.TYPES_MAP = {
            "number": float,
            "hex": str,
            "string": str,
            "name": str,
            "binary": str,
        }

        self.ARRAY_REGEX = r"(?:(?P<pre>[^\\\n]|^)\[(?P<array>.*[^\\])?\])"
        self.SPLIT_REGEX = r"\s+"  # r"(?:\r\n)|\n| |\s"
        self.ID_REGEX = r"ARRAY___\d+|NUMBER___\d+|STRING___\d+|NAME___\d+|BINARY___\d+|HEX___\d+"
        self.BOOL_REGEX = r"true|false"
        # self.HAS_HEX_3 = r"(?P<hex>\\(?:\d{3})(?:\\(?:\d{3})|(?:[^\\])))"
        self.HAS_HEX_3 = (
            r"\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:\\)?.))"
        )
        self.HEX_ITERATE = r"\\(?P<hex>\d{3})|(?P<char>.)"
        self.HEX_ITERATE_V2 = (
            r"\\(?P<hex>\d{3})|(?P<char>.*?(?:(?=\\\d{3})|$))"
        )
        self.HEX_ITERATE_V3 = r"\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:\\)?.(?:(?=\\\d{3})|$)))"
        "\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:.|\\\\)(?:(?=\\\d{3})|$)))"

        self.primatives_counter = 0
        self.arrays_counter = 0
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
                arguements.append(self.variables_dict[token])

            elif token.lstrip(")") in PdfOperator.OPERTORS_SET:
                cmd = token.lstrip(")")
                command = PdfOperator(cmd, arguements)
                # print(f"{cmd} ( {', '.join(list(map(str,arguements)))} )")
                arguements = []
                yield command
            else:
                print("----", token)
        self.tokens = []

    PRINTABLE = string.ascii_letters + string.digits + string.punctuation + " "

    # def clean_hex_in_string(self, text: str) -> str:
    #     matches = re.findall(self.HAS_HEX_3,text,re.DOTALL)
    #     if len(matches) >= 2:
    #         for m in re.it

    def hex_escape(self, s):
        return "".join(
            (
                c
                if c in PDFStreamParser.PRINTABLE
                else r"\x{0:02x}".format(ord(c))
            )
            for c in s
        )

    def parse_stream(self, lines: str):
        self.variables_dict = {}
        self.arrays_counter = 0
        self.primatives_counter = 0

        lines_list = lines.replace("\r", "").split("\n")
        i = 0
        while i < len(lines_list):
            line = lines_list[i]
            if line.strip().endswith("ID"):
                self.__process_line(line.rstrip("ID"))
                # print("found image data")
                binary_data = []
                i += 1
                while i < len(lines_list):
                    sub_line = lines_list[i]
                    if sub_line.startswith("EI"):
                        # print(
                        #     self.hex_escape("".join(binary_data)), "ID", "EI"
                        # )
                        self.primatives_counter += 1
                        name = f"BINARY___{self.primatives_counter}"
                        self.variables_dict[name] = "".join(binary_data)
                        self.tokens.extend([name, "ID", "EI"])
                        self.__process_line(sub_line.lstrip("EI"))
                        break
                    binary_data.append(lines_list[i])
                    i += 1
            else:
                self.__process_line(line)
            i += 1

        return self

    def __process_line(self, line: str):

        m = re.search(
            PdfOperator.INLINE_IMAGE_OPERATORS_REGEX, line, flags=re.MULTILINE
        )
        if m:
            self.__extract_special_operators(m)
            # print("catched operator", m.group("operator"))
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

    def __replace_arrays(self, match):
        self.arrays_counter += 1

        # print(match.groupdict())
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

    def __extract_primatives(
        self, data: str | None = None, primatives_array=None
    ):
        if data is None:
            data = self.data
        # self.primatives_counter = 0
        # self.variables_dict = {}
        new_string = re.sub(
            self.PRIMATIVE_REGEX,
            lambda m: self.__replace_primatives(m, primatives_array),
            data,
            flags=re.MULTILINE | re.DOTALL,
        )

        return new_string

    def __replace_hex_in_string(self, match: re.Match):
        int1, int2 = 0, 0
        hex1 = match.groupdict().get("hex1", "").strip("\\")
        high_byte = int(hex1, 8)

        char = match.group("char")
        hex2 = match.group("hex2")
        if char:
            if len(char) == 2 and char.startswith("\\"):
                char = char[1:]
            low_byte = ord(char)
        elif hex2:
            low_byte = int(hex2, 8)
        else:
            raise Exception("hex is not valid")
        cid = (high_byte << 8) | low_byte

        return chr(cid)  # f"\\{cid:03d}"

    def pdf_hex_to_str(self, hex_text: str) -> str:
        cleaned = "".join(hex_text.split())
        if len(cleaned) % 2 == 1:
            cleaned += "0"

        if len(cleaned) == 4:
            cleaned = cleaned[2:]
        raw_bytes = bytes.fromhex(cleaned)
        result = raw_bytes.decode("latin-1")
        return result

    def __replace_primatives(self, match, primatives_array):
        self.primatives_counter += 1
        for p_type, p_value in match.groupdict().items():
            if p_value is None:
                continue

            p_type = p_type.replace("O", "")
            value = self.TYPES_MAP[p_type](p_value)
            if p_type == "hex":
                value = self.pdf_hex_to_str(value)
            if p_type.startswith("string") and re.match(self.HAS_HEX_3, value):
                # print("string=", value)
                value = re.sub(
                    self.HEX_ITERATE_V3,
                    self.__replace_hex_in_string,
                    value,
                    flags=re.DOTALL | re.MULTILINE,
                )
                # print("new_string=", value)
            primative_id = f"{p_type.upper()}___{self.primatives_counter}"
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

    """
    Parses PDF streams into executable commands by tokenizing and interpreting PDF syntax.

    Attributes:
        PRIMATIVE_REGEX (str): Regular expression to identify primitive PDF elements such as names, strings, and numbers.
        TYPES_MAP (dict): Mapping of primitive types to their corresponding Python types.
        ARRAY_REGEX (str): Regular expression to detect arrays within the PDF stream.
        SPLIT_REGEX (str): Regular expression used to split the PDF stream into individual tokens.
        ID_REGEX (str): Regular expression to identify variable IDs within the tokenized stream.
        primatives_counter (int): Counter for tracking the number of primitives processed.
        arrays_counter (int): Counter for tracking the number of arrays processed.
        variables_dict (dict): Dictionary storing variables and their corresponding values extracted from the stream.
        data (str): The raw PDF stream data to be parsed.
        tokens (list): List of tokens extracted from the PDF stream after splitting.

    Methods:
        __init__(self):
            Initializes the PDFStreamParser with default regex patterns and counters.

        iterate(self):
            Iterates through the token list, yielding PdfOperator commands based on the parsed tokens.

        jkparse_stream(self, data: str) -> 'PDFStreamParser':
            Parses the provided PDF stream data, extracts arrays and primitives, and tokenizes the stream for processing.

        __extract_arrays(self) -> str:
            Identifies and extracts arrays from the PDF stream, replacing them with unique identifiers and storing them in variables_dict.

        __replace_arrays(self, match) -> str:
            Helper method to replace matched arrays with unique IDs and update variables_dict accordingly.

        __extract_primatives(self, data: str | None = None, primatives_array = None) -> str:
            Extracts primitive elements from the data, replacing them with unique identifiers and storing them as needed.

        __replace_primatives(self, match, primatives_array) -> str:
            Helper method to replace matched primitives with unique IDs and update the relevant storage structures.
    """
