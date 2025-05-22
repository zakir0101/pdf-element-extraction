import pprint
import re
from .pdf_operator import PdfOperator
import string
import os
from .pdf_encoding import PdfEncoding as pnc


class PDFStreamParser:

    def __init__(self):
        OR = "|"
        NOT_ESCAPE = r"(?:[^\\]|[^\\](?:\\{2})+|[\\](?=\)\]\s*TJ))"

        self.HEX_REGEX = r"<(?P<hex>[0-9a-fA-F]+)>"
        self.NAME_REGEX = r"(?P<name>/\w+)"
        self.STRING_REGEX = (
            r"(?:\((?P<string>(?:.*?" + NOT_ESCAPE + r"))(?:\)))"
        )
        self.EMPTY_STRING_REGEX = r"\((?P<stringO>)(?:\))"
        self.BOOL_REGEX = r"(?P<bool>true|false)"
        #  r"(?:\((?P<string>(?:.*?[^\\]))(?=\)))|"
        self.NUMBER_REGEX = r"(?:(?:(?<=[^_\-\n\d\.\w])|^)(?P<number>[\d.]+))|(?P<numberO>-[\d.]+)"
        self.IMAGE_REGEX = r"(?P<image>ID[\s\S]*?)(?=EI)"
        self.INLINE_IMAGE_OP_REGEX = (
            r"(?P<inline>\/(?:W|H|IM|BPC|CS|D|F|DP))(?=\W|$)"  # (?: |^)
        )

        """
<(?P<hex>[0-9a-fA-F]+)>|(?P<name>/\w+)|\((?P<stringO>)(?:\))|(?:\((?P<string>(?:.*?(?:[^\\]|[^\\](?:\\{2})+)))(?:\)))|(?:(?:(?<=[^_\-\n\d\.])|^)(?P<number>(?:-)?[\d.]+))|(?<=ID)(?P<image>[\s\S]*?)(?=EI)
        """
        self.PRIMATIVE_REGEX = (
            self.HEX_REGEX
            + OR
            + self.INLINE_IMAGE_OP_REGEX
            + OR
            + self.NAME_REGEX
            + OR
            + self.STRING_REGEX
            + OR
            + self.EMPTY_STRING_REGEX
            + OR
            + self.BOOL_REGEX
            + OR
            + self.NUMBER_REGEX
            + OR
            + self.IMAGE_REGEX
        )
        self.ARRAY_REGEX = (
            r"(?:(?:(?<=[^\\])|^)\[(?P<array>[\s\S]*?(?:[^\\]|\\{2})?)\])"
        )

        # r"(?:(?:(?<=[^\\])|^)\[(?P<array>.*?(?:[^\\]|\\{2})?)\])"
        # r"(?:(?:(?<=[^\\])|^)\[(?P<array>(?:.*[^\\]))\])"
        # r"^[^(]*(?:(?:(?<=[^\\])|^)(?P<array>\[(?:.*[^\\])?\]))"

        self.DICT_REGEX = r"\s*<<(?P<obj>.*?)>>"  # (?P<name>/\w+)?
        self.DICT_CONTENT = (
            self.NAME_REGEX.replace("name", "key")
            + r"\s*(?:"
            + self.ARRAY_REGEX
            + OR
            + self.PRIMATIVE_REGEX
            + ")"
        )
        self.TYPES_MAP = {
            "number": float,
            "hex": str,
            "image": str,
            "string": str,
            "name": str,
            "inline": str,
            "binary": str,
            "bool": lambda v: True if v == "true" else False,
        }
        self.SPLIT_REGEX = r"\s+"  # r"(?:\r\n)|\n| |\s"
        self.ID_REGEX = r"ARRAY___\d+|DICT___\d+|NUMBER___\d+|STRING___\d+|NAME___\d+|BOOL___\d+|BINARY___\d+|HEX___\d+|IMAGE___\d+"
        self.INLINE_ID_REGEX = r"INLINE___\d+"
        self.TRUNCATED_HEX = r"<[0-9a-fA-F]+\s(?=[0-9a-fA-F]+>)"

        # self.TRUNCATED_TOKEN_REGEX = re.compile(
        #     r"(?:<[^>]*$)",
        #     re.MULTILINE,
        # )
        # self.INVALID_ESCAPE = re.compile(
        #     r"(?:[^\\]|^)\\(?![()\\rntb0-7])", re.MULTILINE | re.DOTALL  # f
        # )
        # self.HAS_HEX_3 = re.compile(
        #     r"(?:\\(?:\d{3})(?:\\(?:\d{3})|(?:(?:\\)?.)))+$", re.MULTILINE
        # )
        # self.HEX_ITERATE = r"\\(?P<hex>\d{3})|(?P<char>.)"
        # self.HEX_ITERATE_V2 = (
        #     r"\\(?P<hex>\d{3})|(?P<char>.*?(?:(?=\\\d{3})|$))"
        # )
        # self.HEX_ITERATE_V3 = r"\\(?P<hex1>\d{3})(?:\\(?P<hex2>\d{3})|(?P<char>(?:\\)?.(?:(?=\\\d{3})|$)))"

        self.primatives_counter = 0
        self.arrays_counter = 0
        self.dict_counter = 0
        self.variables_dict = {}
        self.data: str = ""
        self.tokens = []

    def iterate(self):
        if not self.tokens:
            raise ValueError("No tokens to parse")

        arguements = []
        ignore_next = False
        for idx, token in enumerate(self.tokens):
            if not token:  # or token == ")":
                continue
            if ignore_next:
                ignore_next = False
                continue
            if re.match(self.ID_REGEX, token):
                data = self.variables_dict[token]
                if token.startswith("IMAGE"):
                    img_data = data.lstrip("\n ")[2:].strip("\r\n")
                    command = PdfOperator("ID", [img_data])
                    yield command
                else:
                    arguements.append(data)
            elif re.match(self.INLINE_ID_REGEX, token):
                if len(arguements) > 0:
                    print("args = ", arguements)
                    raise Exception("unhandled args")
                cmd = self.variables_dict[token]
                args = self.variables_dict[self.tokens[idx + 1]]
                command = PdfOperator(cmd, [args])
                ignore_next = True
                yield command
            elif token in PdfOperator.OPERTORS_SET:  # .lstrip() in
                cmd = token  # .lstrip(")")
                command = PdfOperator(cmd, arguements)
                arguements = []
                yield command
            else:
                print("----", token)
                mi = max(idx - 10, 0)
                ma = min(idx + 10, len(self.tokens))
                token_range = self.tokens[mi:ma]
                token_resolved = [
                    (self.variables_dict.get(s) or s) for s in token_range
                ]
                print("prev_token", token_resolved)
                raise Exception("----" + token)
        self.tokens = []

    def parse_stream(self, stream_content: str):
        self.variables_dict = {}
        self.arrays_counter = 0
        self.dict_counter = 0
        self.primatives_counter = 0
        stream_content = stream_content.replace("\\\r", "")
        stream_content = re.sub(
            self.TRUNCATED_HEX,
            lambda m: m.group(0).strip("\n"),  # \r
            stream_content,
            flags=re.DOTALL | re.MULTILINE,
        )

        def replace_primatives_v2(match: re.Match):
            for p_type, p_value in match.groupdict().items():
                if p_value is None:
                    continue

                self.primatives_counter += 1
                p_type = p_type.replace("O", "")
                value = self.TYPES_MAP[p_type](p_value)

                if p_type.startswith("string"):
                    value = value.replace("\\(", "(").replace("\\)", ")")
                    value = re.sub(
                        r"\\([1234567]{3})",
                        lambda m: pnc.octal_to_char(m.group(1)),
                        value,
                        flags=re.DOTALL | re.MULTILINE,
                    )
                elif p_type == "hex":
                    value = re.sub(
                        r"([0-9a-fA-F]{2})",
                        lambda m: pnc.hex_to_char(m.group(1)),
                        value,
                        flags=re.DOTALL | re.MULTILINE,
                    )

                primative_id = (
                    f"{p_type.upper()}___{self.primatives_counter:06}"
                )
                self.variables_dict[primative_id] = value
                return f" {primative_id} "
            return " "

        def replace_array_v2(match: re.Match):
            p_value = match.group("array")
            if p_value is None:
                return ""  # WARN: potential bug

            self.arrays_counter += 1
            array = []
            for prim_key in p_value.replace("\n", "").split(" "):
                if prim_key:  # WARN:
                    if prim_key in self.variables_dict:
                        prim_value = self.variables_dict.pop(prim_key)
                        array.append(prim_value)
                    else:
                        print("match = ", match.group("array"))
                        print("error_key =", prim_key)
                        raise Exception
            # print(array)
            array_id = f"ARRAY___{self.arrays_counter}"
            self.variables_dict[array_id] = array
            return f" {array_id} "

        def replace_dict_v2(match: re.Match):
            p_value = match.group("obj")
            if p_value is None:
                return ""  # WARN: potential bug
            # print(match.group(0))
            self.dict_counter += 1
            dict_obj = {}
            current_Key = None
            for prim_key in p_value.replace("\n", "").split(" "):
                if not prim_key:
                    continue
                if prim_key not in self.variables_dict:
                    print("match = ", match.group("obj"))
                    print("error_key =", prim_key)
                    raise Exception
                if current_Key:
                    dict_obj[current_Key] = self.variables_dict.pop(prim_key)
                    current_Key = None
                else:
                    current_Key = self.variables_dict.pop(prim_key)

            dict_id = f"DICT___{self.dict_counter}"
            self.variables_dict[dict_id] = dict_obj
            return f" {dict_id} "

        stream_content = re.sub(
            self.PRIMATIVE_REGEX,
            replace_primatives_v2,
            stream_content,
            flags=re.DOTALL | re.MULTILINE,
        )

        # print(stream_content)
        # print("\n" * 4)
        stream_content = re.sub(
            self.ARRAY_REGEX,
            replace_array_v2,
            stream_content,
            flags=re.DOTALL | re.MULTILINE,
        )

        # print(stream_content)

        stream_content = re.sub(
            self.DICT_REGEX,
            replace_dict_v2,
            stream_content,
            flags=re.DOTALL | re.MULTILINE,
        )

        self.tokens.extend(
            re.split(
                self.SPLIT_REGEX,
                stream_content,
                flags=re.MULTILINE | re.DOTALL,
            )
        )
        return self

    def parse_stream_old(self, lines: str):
        # lines = lines.replace("\r", "")
        self.variables_dict = {}
        self.arrays_counter = 0
        self.dict_counter = 0
        self.primatives_counter = 0

        # TODO: user regex to fetch all \t\n\r\b and replace them with the actual control char
        lines_list = (
            lines
            # .replace("\\b", "\b")
            # .replace("\\t", "\t")
            .replace("\\\r", "").split("\n")
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

    def __extract_arrays(
        self,
    ):
        # if data is None:
        #     data = self.data
        new_string = re.sub(
            self.ARRAY_REGEX,
            lambda m: self.__replace_arrays(m)[0],
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

    def __replace_arrays(self, match: re.Match):
        self.arrays_counter += 1

        array_id = f"ARRAY___{self.arrays_counter}"
        all_text = match.group(0)
        array = match.group("array")
        pre_text = all_text.replace(array, "")
        array = array.strip("[]")
        if not array:
            self.variables_dict[array_id] = []
            return f"{pre_text}  {array_id}   ", []
        parsed_array = []
        self.__extract_primatives(array, parsed_array)
        self.variables_dict[array_id] = parsed_array
        replacement = f"{pre_text}  {array_id}  "
        # if only_replace:
        #     return replacement
        return replacement, parsed_array

    def __replace_dicts(self, match):
        self.dict_counter += 1
        dict_id = f"DICT___{self.dict_counter}"
        # dict_name = match.group("name") or "UNKOWN"
        dict_str = match.group("obj")
        output_dict = self.__extract_dict_object(dict_str)
        self.variables_dict[dict_id] = output_dict  # {dict_name: output_dict}
        return f" {dict_id} "  # {dict_name}

    def __extract_dict_object(self, content: str):
        output: dict = {}
        for match in re.finditer(
            self.DICT_CONTENT,
            content,
            flags=re.MULTILINE | re.DOTALL,
        ):
            key = match.group("key")
            value_type = match.lastgroup
            if value_type == "array":
                arr_name, value = self.__replace_arrays(match)
            else:
                value = match.group(value_type)
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
        int1, int2 = 0, 0
        hex1 = match.groupdict().get("hex1", "").strip("\\")

        hex2 = match.group("hex2")
        char = match.group("char")
        if char:
            if len(char) == 2 and char.startswith("\\"):
                char = char[1:]
            byte_data = pnc.char_to_byte(char)
            byte_string = pnc.byte_to_octal(byte_data)
            hex2 = byte_string.lstrip("0o").lstrip("\\")
        final = f"\\{hex1}\\{hex2}"
        return final

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
