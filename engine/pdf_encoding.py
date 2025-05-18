import os

if os.name == "nt":  # Windows
    enc = "ansi"
else:
    enc = "latin1"


class PdfEncoding:
    LATIN_ENC = "latin1"
    ANSI_ENC = "ansi"
    CURRENT_ENCODING = enc

    @classmethod
    def is_valid_byte(cls, b: bytes | int):
        if not isinstance(b, (int, bytes)):
            raise Exception("is not single byte")
        c = b
        if isinstance(b, bytes):
            if not len(b) == 1:
                raise Exception("is not single byte")
            c = b[0]
        if c > 255:
            raise Exception("byte is > 255 !")
        return True

    @classmethod
    def is_valid_char(cls, b: str):
        if not len(b) == 1:
            raise Exception("is not single char")

    @classmethod
    def char_to_byte(cls, char: str):
        cls.is_valid_char(char)
        b = char.encode(cls.CURRENT_ENCODING)
        return b

    @classmethod
    def byte_to_octal(cls, b: bytes | int):
        cls.is_valid_byte(b)
        c = b
        if isinstance(b, bytes):
            c = b[0]
        return f"\\{c:03o}"

    @classmethod
    def bytearray_to_octal(cls, b_array: bytes | int):
        return "".join([f"\\{c:03o}" for c in b_array])

    @classmethod
    def char_to_int(cls, char):
        return cls.char_to_byte(char)[0]

    @classmethod
    def int_to_char(cls, n: int):
        b = int.to_bytes(n)
        cls.is_valid_byte(b)
        return b.decode(cls.CURRENT_ENCODING)

    @classmethod
    def bytes_to_string(cls, byte_text: bytes):
        if not isinstance(byte_text, (bytes, bytearray)):
            raise Exception("the input bytes are not of correct type")
        for b in byte_text:
            cls.is_valid_byte(b)
        return byte_text.decode(enc)

    @classmethod
    def string_to_bytes(cls, text: str):
        return text.encode(cls.CURRENT_ENCODING)


def test():
    for enc1 in ["utf-8", enc]:
        print(f"\n\n********** {enc1} **********")
        x = "abcÄÖÜ"
        bx = x.encode(enc1)
        print("number of bytes = ", len(bx))
        print("bytes", bx)

        intx = [b for b in bx]
        print(intx)
        y = "F"
        y_d = y.encode(enc1)
        print("y =", y)
        print("y_enceded", y_d)
        print("y_enceded_to_int", int.from_bytes(y_d))
        print("y_enceded_get_first", y_d[0])


if __name__ == "__main__":
    test()
