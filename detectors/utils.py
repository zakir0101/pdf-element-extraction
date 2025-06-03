import os


# *********************************************************
# *****************++ Numeric, Roman and Alphabet numbering
# ******************* Handler :


def get_alphabet(number):
    # index = ord('a') + (number - 1 )
    return chr(number - 1 + 97)


def get_roman(number):
    num = [1, 4, 5, 9, 10, 40, 50, 90, 100, 400, 500, 900, 1000]
    sym = [
        "I",
        "IV",
        "V",
        "IX",
        "X",
        "XL",
        "L",
        "XC",
        "C",
        "CD",
        "D",
        "CM",
        "M",
    ]
    i = 12
    # number = number + 1
    result = ""
    while number:
        div = number // num[i]
        number %= num[i]

        while div:
            result += sym[i]
            div -= 1
        i -= 1

    return result.lower()


def checkIfRomanNumeral(numeral: str):
    """Controls that the userinput only contains valid roman numerals"""
    numeral = numeral.upper()
    validRomanNumerals = ["X", "V", "I"]
    valid = True
    for letters in numeral:
        if letters not in validRomanNumerals:
            valid = False
            break
    return valid


def value(r):
    if r == "I":
        return 1
    if r == "V":
        return 5
    if r == "X":
        return 10
    if r == "L":
        return 50
    if r == "C":
        return 100
    if r == "D":
        return 500
    if r == "M":
        return 1000
    return -1


def romanToDecimal(str):
    res = 0
    i = 0

    while i < len(str):
        # Getting value of symbol s[i]
        s1 = value(str[i])

        if i + 1 < len(str):
            # Getting value of symbol s[i + 1]
            s2 = value(str[i + 1])

            # Comparing both values
            if s1 >= s2:
                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s1
                i = i + 1
            else:
                # Value of current symbol is greater
                # or equal to the next symbol
                res = res + s2 - s1
                i = i + 2
        else:
            res = res + s1
            i = i + 1

    return res


def alpha_roman_to_decimal(charac):
    """
    convert alpha / roman number to decimals , starting from 0 == a or i
    """
    is_roman = checkIfRomanNumeral(charac)
    if is_roman:
        num = romanToDecimal(charac.upper())
    elif len(charac) == 1:
        num = ord(charac) - 96
    else:
        raise Exception
    return num - 1


def get_next_label_old(prev: str):
    is_roman = checkIfRomanNumeral(prev)
    if is_roman:
        num = romanToDecimal(prev.upper())
        next = get_roman(num + 1)
    elif len(prev) == 1:
        num = ord(prev)
        next = get_alphabet(num - 96 + 1)
    else:
        raise Exception
    return next


NUMERIC = 1
ALPHAPET = 2
ROMAN = 3


def get_next_label(prev, system):
    prev = str(prev)
    if prev.isdigit() and system == NUMERIC:
        prev = int(prev)
        prev += 1
        return prev
    elif type(prev) is str and system == ROMAN:
        num = romanToDecimal(prev.upper())
        return get_roman(num + 1)
    elif type(prev) is str and len(prev) == 1 and system == ALPHAPET:
        num = ord(prev)
        return get_alphabet(num - 96 + 1)
    else:
        raise Exception


def is_first_label(input: str):
    return input == "i" or input == "a"


SEP = os.path.sep
