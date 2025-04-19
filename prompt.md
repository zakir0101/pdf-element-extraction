# Prompt :

I am trying to analyze a row (binary) pdf file , to extract certain parts of it and sotre it and later inject it to my own pdf...

for these case I had to understand how row pdf file are structured , so I wrote this script parser.py , which take a pdf file and print the content of its stream object after parsing it.

```

import re
import argparse
import sys
from PyPDF2 import PdfReader
from PyPDF2.generic import EncodedStreamObject, ArrayObject


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Parse a PDF's objects and content streams and produce a human-readable output."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to the input PDF file"
    )
    parser.add_argument(
        "--output", "-o", required=True, help="Path to the output text or md file"
    )
    parser.add_argument(
        "--start-page", type=int, default=None, help="Start page number (1-based)"
    )
    parser.add_argument(
        "--end-page", type=int, default=None, help="End page number (1-based)"
    )
    return parser.parse_args()


def print_dict(obj, indent=0, f=sys.stdout):
    prefix = "  " * indent
    if isinstance(obj, dict):
        f.write(prefix + "{Dictionary}:\n")
        for k, v in obj.items():
            f.write(prefix + f"  Key: {k}\n")
            print_dict(v, indent + 2, f=f)
    elif isinstance(obj, list):
        f.write(prefix + "{Array}:\n")
        for i, item in enumerate(obj):
            f.write(prefix + f"  Index {i}:\n")
            print_dict(item, indent + 2, f=f)
    else:
        f.write(prefix + f"{repr(obj)}\n")


def interpret_operator(op, operands):
    explanations = {
        "Tf": "Set text font and size",
        "Tj": "Show text",
        "TJ": "Show text array (with possible kerning)",
        "Td": "Move text position",
        "TD": "Move text position and set leading",
        "Tm": "Set text matrix and text line matrix",
        "BT": "Begin text object",
        "ET": "End text object",
        "Tc": "Set character spacing",
        "Tw": "Set word spacing",
        "T*": "Move to start of next text line",
        "Do": "Draw an XObject (image or form)",
        "q": "Save graphics state",
        "Q": "Restore graphics state",
        "cm": "Concatenate matrix to current transform matrix",
        # Newly added:
        "EMC": "End Marked Content",
        "gs": "Set Graphics State",
        "BI": "Begin Inline Image",
        "ID": "Begin Image Data for Inline Image",
        "EI": "End Inline Image",
        "g": "Set Gray Level (non-stroking)",
    }

    # Format operands into a single string: operand1, operand2, ...
    operands_str = ", ".join(operands)

    # If this token does not match a known operator, check if it's truly an operator or just data
    if op not in explanations:
        # If it's a known non-operator token like 'true', 'None', just format accordingly
        # but since we treat every op here as operator, we just mark unknown ones:
        if op in ["true", "None"]:
            return f"{op}({operands_str}) // Not an operator, likely a boolean or parsing artifact"
        else:
            return f"{op}({operands_str}) // Unknown operator"

    return f"{op}({operands_str}) // {explanations[op]}"


regexTJ = r"(?P<arg>\[.*\])(?P<cmd>\w{2})"


def tokenize_content_stream(data):
    # A naive tokenizer that splits on whitespace.
    # Real PDF parsing would need more robust handling.
    raw_tokens = data.replace(b"\r", b"").split(b"\n")
    flat_tokens = []
    for line in raw_tokens:
        line_encoded = line.decode("latin1", "replace")
        match = re.search(regexTJ, line_encoded)
        if match:
            flat_tokens.append(match.group("arg"))
            flat_tokens.append(match.group("cmd"))
        else:
            parts = line_encoded.strip().split(" ")
            for p in parts:
                if p:
                    flat_tokens.append(p)

    tokens = []
    current_operands = []
    for tk in flat_tokens:
        # t_str = tk.decode('latin1', 'replace').strip()
        t_str = tk.strip()
        # Check if token looks like an operator:
        # We guess operators are alphabetic or in a known set (BT, ET, T*)
        str_match = re.match(r"([\(\[].*[\)\]])(T.*)", t_str)
        if str_match:
            current_operands = []
            operand = str_match.group(1)
            operator = str_match.group(2)
            tokens.append((operator, [operand]))
        elif t_str.isalpha() or t_str in ["BT", "ET", "T*"]:
            # Operator found, store previous operands and start fresh
            tokens.append((t_str, current_operands))
            current_operands = []
        else:
            # Operand
            current_operands.append(t_str)
    return tokens


def extract_content_streams(page):
    """
    Return a list of decoded byte strings for the page's content streams.
    """
    contents = page.get("/Contents")
    streams_data = []
    if contents is None:
        return streams_data

    # Resolve if indirect
    if hasattr(contents, "get_object"):
        contents = contents.get_object()

    if isinstance(contents, EncodedStreamObject):
        data = contents.get_data()
        if data:
            streams_data.append(data)
    elif isinstance(contents, ArrayObject):
        for c in contents:
            if hasattr(c, "get_object"):
                c = c.get_object()
            if isinstance(c, EncodedStreamObject):
                data = c.get_data()
                if data:
                    streams_data.append(data)
    # If it's something else (like a different type of object), we might skip it.
    return streams_data


def main():
    args = parse_arguments()
    input_pdf = args.input
    output_file = args.output
    start_page = args.start_page
    end_page = args.end_page

    reader = PdfReader(input_pdf)

    if start_page is None:
        start_page = 1
    if end_page is None:
        end_page = len(reader.pages)

    if start_page < 1 or end_page > len(reader.pages):
        print("Invalid page range specified.")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# PDF Analysis Report\n\n")
        f.write(f"Input File: {input_pdf}\n")
        f.write(f"Pages Analyzed: {start_page} to {end_page}\n\n")

        # Print high-level PDF structure (trailer, etc.)
        f.write("## Document Trailer (High-level)\n")
        print_dict(reader.trailer, f=f)
        f.write("\n")

        # Iterate over each page
        for page_number in range(start_page, end_page + 1):
            page = reader.pages[page_number - 1]
            f.write(f"\n## Page {page_number}\n")

            # Print Page Dictionary
            f.write("### Page Dictionary\n")
            print_dict(page, f=f)

            # Extract Content Streams
            content_streams = extract_content_streams(page)
            if content_streams:
                for idx, cs_data in enumerate(content_streams, start=1):
                    f.write(f"\n### Content Stream {idx}\n")
                    f.write("Raw Data (snippet):\n\n")
                    snippet = cs_data.decode("latin1", "replace")[:500]
                    f.write(snippet + "...\n\n")
                    tokens = tokenize_content_stream(cs_data)
                    f.write("**Operators and Operands**:\n\n")
                    for op, operands in tokens:
                        explanation = interpret_operator(op, operands)
                        f.write(explanation + "\n")
            else:
                f.write("### Content Stream\n")
                f.write("No content streams found or could not decode.\n")

    print(f"Analysis written to {output_file}")


if __name__ == "__main__":
    main()

```


and here is and example of the output ....

```

# PDF Analysis Report

Input File: .\9702_m23_qp_12.pdf
Pages Analyzed: 3 to 4

## Document Trailer (High-level)
{Dictionary}:
  Key: /Size
    324
  Key: /Info
    IndirectObject(143, 0, 2878396841808)
  Key: /Root
    IndirectObject(146, 0, 2878396841808)
  Key: /ID
    {Array}:
      Index 0:
        'b\x0bµ{d\x04gžáªØÂö¥r6'
      Index 1:
        '|ê»ìÿi¢âÞR?ÓFÒô¯'


## Page 3
### Page Dictionary
{Dictionary}:
  Key: /Type
    '/Page'
  Key: /Parent
    IndirectObject(140, 0, 2878396841808)
  Key: /Resources
    {Dictionary}:
      Key: /Font
        {Dictionary}:
          Key: /TT0
            IndirectObject(172, 0, 2878396841808)
          Key: /TT1
            IndirectObject(166, 0, 2878396841808)
          Key: /TT2
            IndirectObject(162, 0, 2878396841808)
          Key: /TT3
            IndirectObject(103, 0, 2878396841808)
          Key: /T1_0
            IndirectObject(164, 0, 2878396841808)
      Key: /ExtGState
        IndirectObject(226, 0, 2878396841808)
      Key: /ProcSet
        {Array}:
          Index 0:
            '/PDF'
          Index 1:
            '/Text'
  Key: /Contents
    IndirectObject(224, 0, 2878396841808)
  Key: /MediaBox
    {Array}:
      Index 0:
        0
      Index 1:
        0
      Index 2:
        595
      Index 3:
        842
  Key: /CropBox
    {Array}:
      Index 0:
        0
      Index 1:
        0
      Index 2:
        595
      Index 3:
        842
  Key: /Rotate
    0
  Key: /TrimBox
    {Array}:
      Index 0:
        0
      Index 1:
        0
      Index 2:
        595
      Index 3:
        842
  Key: /BleedBox
    {Array}:
      Index 0:
        0
      Index 1:
        0
      Index 2:
        595
      Index 3:
        842
  Key: /LastModified
    'D:20220809075413Z'

### Content Stream 1
Raw Data (snippet):

0 g
1 i 

/GS0 gs
BT
/TT0 1 Tf
10.9756 0 0 10.98 294.60001 795.7403 Tm
(3)Tj
/TT1 1 Tf
10.01601 0 0 10.02 300.72 795.7403 Tm
( )Tj
/TT2 1 Tf
10.9756 0 0 10.98 502.2599 795.7403 Tm
( )Tj
/TT1 1 Tf
10.01601 0 0 10.02 49.62 784.16029 Tm
( )Tj
/TT2 1 Tf
0.0006 Tc -0.00011 Tw 7.9767 0 0 7.98 49.62 38.3604 Tm
[(\251 UCLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)-7( )]TJ
/TT0 1 Tf
0.0011 Tc 10.9756 0 0 10.98 491.28 38.3604 Tm
([Turn over)Tj
/TT2 1 Tf
0 Tc 0 Tw 7.9767 0 0 7.98 545.7 38.3604 Tm
( )Tj...

**Operators and Operands**:

g(0) // Set Gray Level (non-stroking)
i(1) // Unknown operator
gs(/GS0) // Set Graphics State
BT() // Begin text object
Tf(/TT0, 1) // Set text font and size
Tm(10.9756, 0, 0, 10.98, 294.60001, 795.7403) // Set text matrix and text line matrix
Tj((3)) // Show text
Tf(/TT1, 1) // Set text font and size
Tm(10.01601, 0, 0, 10.02, 300.72, 795.7403) // Set text matrix and text line matrix
Tf((, )Tj, /TT2, 1) // Set text font and size
Tm(10.9756, 0, 0, 10.98, 502.2599, 795.7403) // Set text matrix and text line matrix
Tf((, )Tj, /TT1, 1) // Set text font and size
Tm(10.01601, 0, 0, 10.02, 49.62, 784.16029) // Set text matrix and text line matrix
Tf((, )Tj, /TT2, 1) // Set text font and size
Tc(0.0006) // Set character spacing
Tw(-0.00011) // Set word spacing
Tm(7.9767, 0, 0, 7.98, 49.62, 38.3604) // Set text matrix and text line matrix
TJ([(\251 UCLES 202)-7(3)-7( )-20429(9702/12/F/)-7(M)-1(/23)-7( )]) // Show text array (with possible kerning)
Tf(/TT0, 1) // Set text font and size
Tc(0.0011) // Set character spacing
Tm(10.9756, 0, 0, 10.98, 491.28, 38.3604) // Set text matrix and text line matrix
Tf(([Turn, over)Tj, /TT2, 1) // Set text font and size
Tc(0) // Set character spacing
Tw(0) // Set word spacing
Tm(7.9767, 0, 0, 7.98, 545.7, 38.3604) // Set text matrix and text line matrix
Tf((, )Tj, /TT0, 1) // Set text font and size
Tm(10.9756, 0, 0, 10.98, 49.62, 769.4003) // Set text matrix and text line matrix
Tj((1)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.00121) // Set character spacing
Tw(-0.0002) // Set word spacing
Td(0.5576, 0) // Move text position
TJ([( )-1099(What represents a physical quantity)9(? )]) // Show text array (with possible kerning)
Tf(/TT0, 1) // Set text font and size
Tc(0) // Set character spacing
Tw(0) // Set word spacing
Td(1.37759, -2.14751) // Move text position
Tj((A)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.0013) // Set character spacing
Tw(0.93449) // Set word spacing
Td(0.7216, 0) // Move text position
Tf((, 3.0, )Tj, /TT0, 1) // Set text font and size
Tc(0) // Set character spacing
Tw(0) // Set word spacing
Td(-0.7216, -1.9727) // Move text position
Tj((B)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.00121) // Set character spacing
Tw(0.9346) // Set word spacing
Td(0.7216, 0) // Move text position
kilogram(() // Unknown operator
Tf()Tj, /TT0, 1) // Set text font and size
Tc(0) // Set character spacing
Tw(0) // Set word spacing
Td(-0.7216, -1.9727) // Move text position
Tj((C)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.0013) // Set character spacing
Tw(0.93449) // Set word spacing
Td(0.7216, 0) // Move text position
Tc((, 7.0)Tj, 0) // Set character spacing
Tw(0) // Set word spacing
Tm(5.5177, 0, 0, 5.52, 107.39999, 702.50031) // Set text matrix and text line matrix
Tc((, )Tj, -0.0006) // Set character spacing
Tm(10.9756, 0, 0, 10.98, 108.96001, 702.50031) // Set text matrix and text line matrix
Tf((N, )Tj, /TT0, 1) // Set text font and size
Tc(0) // Set character spacing
Td(-3.4659, -1.9727) // Move text position
Tj((D)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.00169) // Set character spacing
Tw(0.9341) // Set word spacing
Td(0.7216, 0) // Move text position
Tc((, 40%, )Tj, 0) // Set character spacing
Tw(0) // Set word spacing
Td(-2.66229, -1.153) // Move text position
TD((, )Tj, 0, -1.14751) // Move text position and set leading
Tf((, )Tj, /TT0, 1) // Set text font and size
TD(0, -1.153) // Move text position and set leading
Tj((2)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.0013) // Set character spacing
Tw(-0.00031) // Set word spacing
Td(0.5576, 0) // Move text position
TJ([( )-1104(The relation)5(ship betwee)5(n the variables )]) // Show text array (with possible kerning)
Tf(/TT3, 1) // Set text font and size
Tc(0) // Set character spacing
Tw(0) // Set word spacing
Tm(10.94389, 0, 0, 10.9481, 262.32001, 642.9203) // Set text matrix and text line matrix
Tj((D)) // Show text
Tf(/TT2, 1) // Set text font and size
Tc(0.0013) // Set character spacing
Tw(-0.00031) // Set word spacing
Tm(10.9756, 0, 0, 10.98, 270.24001, 642.9203) // Set text matrix and text line matrix
and(() // Unknown operator


```


but as you can see its not very helpfull , I need to improve my function "interpret_operator" to be able to print more helpfull command, like :

1. whenever there is a position or and area defined I do not want to see absolut value , I need a relative values , like position y = 9.9% , then I know its the bottom of the page , or position x = 50% , then I know its the center of the page.

2. I also want the explanation to include the argument values , for example if the operator is "Tm" and the arguments are "10.9756, 0, 0, 10.98, 294.60001, 795.7403" , I want the explanation to be like this "Tm(10.9756, 0, 0, 10.98, 294.60001, 795.7403) // Set text matrix and text line matrix"
