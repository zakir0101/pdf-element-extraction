import unittest
from .pdf_detectors import QuestionDetectorV2, checkIfRomanNumeral 
from models.core_models import Symbol, SymSequence # Added
from models.question import QuestionBase # Added

class TestExtractNumberingPattern(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.detector = QuestionDetectorV2()

    def test_basic_numeric(self):
        print("Running test_basic_numeric...")
        test_cases = {
            "1.": (None, "1", "."),
            " 1. ": (None, "1", "."),
            "2)": (None, "2", ")"),
            "03.": (None, "03", "."),
            "123)": (None, "123", ")"),
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_prefixed_numeric(self):
        print("Running test_prefixed_numeric...")
        test_cases = {
            "Question 1.": ("Question", "1", "."),
            "Q2)": ("Q", "2", ")"),
            "Paper 3.": (None, None, None), # "Paper" is not a prefix, "3." is not at line start
            "Question 04)": ("Question", "04", ")"),
            "Q 5.": ("Q", "5", "."),
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_alphabetic(self):
        print("Running test_alphabetic...")
        test_cases = {
            "a.": (None, "a", "."),
            " (b) ": (None, "b", ")"), 
            "C.": (None, "C", "."),
            " D) ": (None, "D", ")"), 
            "(e).": (None, "e", "."),
            "f": (None, "f", None),
            " g ": (None, "g", None),
            "(H)": (None, "H", ")"), 
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_prefixed_alphabetic(self):
        print("Running test_prefixed_alphabetic...")
        test_cases = {
            "Part a.": ("Part", "a", "."),
            "Section B)": (None, None, None), 
            "Part C. ": ("Part", "C", "."),
            "Part (d)": ("Part", "d", ")"),
            "Part (e).": ("Part", "e", "."),
            "Part f": ("Part", "f", None), 
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_roman(self):
        print("Running test_roman...")
        test_cases = {
            "i.": (None, "i", "."),
            " (ii) ": (None, "ii", ")"), 
            "IV.": (None, "IV", "."),
            " (V) ": (None, "V", ")"),   
            "ix.": (None, "ix", "."),
            "XI)": (None, "XI", ")"), 
            "xxv.": (None, "xxv", "."), 
            "CM)": (None, "CM", ")"),
            "(vii).": (None, "vii", "."), 
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                if expected[1] and not checkIfRomanNumeral(expected[1]): # checkIfRomanNumeral from pdf_utils
                    print(f"Warning: Test case '{line}' has Roman numeral '{expected[1]}' that checkIfRomanNumeral fails for (according to current util).")
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)
    
    def test_invalid_roman_like(self):
        print("Running test_invalid_roman_like...")
        test_cases = {
            "ivx.": (None, None, None), 
            "IC)": (None, None, None),  
            "MMMM.": (None, None, None), 
            "vx.": (None, None, None), 
            "(MMMM).": (None, None, None), 
            "(VX).": (None, None, None),
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_prefixed_roman(self):
        print("Running test_prefixed_roman...")
        corrected_test_cases = { 
            "Part i.": ("Part", "i", "."),
            "Item C.": (None, None, None),    
            "Article iv)": (None, None, None), 
            "Part X.": ("Part", "X", "."),
            "Part (ii)": ("Part", "ii", ")"),
            "Part (ix).": ("Part", "ix", "."),
        }
        for line, expected in corrected_test_cases.items(): 
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_no_pattern(self):
        print("Running test_no_pattern...")
        test_cases = {
            "This is a normal line.": (None, None, None),
            "": (None, None, None),
            "  ": (None, None, None),
            ".1": (None, None, None),
            ")a": (None, None, None),
            "Question without number": (None, None, None), 
            "Q without number": (None, None, None), 
            "Part without letter/roman": (None, None, None), 
            "Alpha": (None, None, None), 
            "The": (None, None, None), 
            "C": (None, "C", None), 
            "C ": (None, "C", None), 
            "(C)": (None, "C", ")"), 
            "C Then some words": (None, None, None), 
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_pattern_with_extra_text(self):
        print("Running test_pattern_with_extra_text...")
        test_cases = {
            "1. This is a question": (None, "1", "."),
            "a) Part a then text": (None, "a", ")"), 
            "iv. Subpart iv here": (None, "iv", "."), 
            "Question 10. And more text": ("Question", "10", "."), 
            "Part B) some details": ("Part", "B", ")"), 
            "(c) Test with parens": (None, "c", ")"), 
            "C. Then some words": (None, "C", "."), 
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

    def test_edge_cases_spacing(self):
        print("Running test_edge_cases_spacing...")
        test_cases = {
            "1 .": (None, "1", "."),
            "a )": (None, "a", ")"),
            "i . ": (None, "i", "."), 
            " Q 1 .": ("Q", "1", "."), 
            " Part a ) ": ("Part", "a", ")"),
        }
        for line, expected in test_cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.detector._extract_numbering_pattern(line), expected)

class TestQuestionHierarchicalDetection(unittest.TestCase):

    def setUp(self):
        self.detector = QuestionDetectorV2()
        self.page_width = 600.0
        self.page_height = 800.0
        self.detector.attach(self.page_width, self.page_height)
        # Reset detector state for each test method explicitly
        self.detector.questions_list = []
        self.detector.current_question_level_0 = None
        self.detector.current_question_level_1 = None
        self.detector.current_question_level_2 = None
        self.detector.current_page_number = -1
        self.detector.processed_lines = []
        self.detector.current_line_symbols = []
        self.detector.last_symbol_on_line = None


    def _create_sym_sequence(self, text: str, x: float, y: float, char_width: float = 6.0, char_height: float = 10.0) -> SymSequence:
        symbols = []
        current_x = x
        if not text: # Handle empty text if necessary, though SymSequence might not allow empty list
             # For this test, we assume text is non-empty or SymSequence handles it.
             # Alternatively, return an empty SymSequence if your SymSequence class supports it,
             # or raise an error/return None if it's an invalid state for these tests.
             # Based on SymSequence constructor, it raises Exception on empty list.
             # So, we should ensure non-empty text for this helper in test context.
            if not text:
                # Create a dummy symbol if text is empty, as SymSequence([]) raises Exception
                # This is a workaround for the test helper, real SymSequence should not be empty.
                # symbols.append(Symbol(" ", current_x, y, 0, char_height)) # Or handle upstream
                pass # Let it proceed and potentially fail if SymSequence requires non-empty

        for char_val in text:
            symbols.append(Symbol(char_val, current_x, y, char_width, char_height))
            current_x += char_width
        
        if not symbols: # If text was empty and we didn't add a dummy symbol
            # This case should ideally not be hit if we always pass non-empty text
            # or if SymSequence could handle empty lists (it can't per current model).
            # For robust testing, one might need a SymSequence that can be empty or skip handle_sequence.
            # For now, assuming test design provides non-empty text to this helper.
            # To make it runnable if an empty text is passed, we could return a SymSequence with a space.
            # This would mean an "empty line" is actually a line with a space.
            # However, QuestionDetectorV2 line assembly would skip truly empty symbol lists anyway.
            # Let's make it so it can return something SymSequence can be made from, even if trivial.
            symbols.append(Symbol(" ", x, y, 0, char_height)) # Default for empty text

        return SymSequence(symbols)

    def test_full_question_hierarchy_mocked(self):
        print("Running test_full_question_hierarchy_mocked...")

        # Page 1
        self.detector.current_page_number = 1 # Manually set for clarity, though handle_sequence does it
        seq1_p1 = self._create_sym_sequence("1. Main Question One", x=50, y=50)
        self.detector.handle_sequence(seq1_p1, page=1)
        seq2_p1 = self._create_sym_sequence("Some text for question one.", x=50, y=65) # Non-numbering line
        self.detector.handle_sequence(seq2_p1, page=1)
        seq3_p1 = self._create_sym_sequence("a) Part A of Q1", x=70, y=80)
        self.detector.handle_sequence(seq3_p1, page=1)
        seq4_p1 = self._create_sym_sequence("i) Sub-part i of Part A", x=90, y=95)
        self.detector.handle_sequence(seq4_p1, page=1)
        seq5_p1 = self._create_sym_sequence("ii) Sub-part ii of Part A", x=90, y=110)
        self.detector.handle_sequence(seq5_p1, page=1)
        seq6_p1 = self._create_sym_sequence("b) Part B of Q1", x=70, y=125)
        self.detector.handle_sequence(seq6_p1, page=1)

        # Page 2
        self.detector.current_page_number = 2 # Manually set for clarity
        self.detector.attach(self.page_width, self.page_height) # Re-attach for new page context if needed by detector
        seq1_p2 = self._create_sym_sequence("Some more text for Part B on page 2.", x=70, y=50)
        self.detector.handle_sequence(seq1_p2, page=2)
        seq2_p2 = self._create_sym_sequence("2. Main Question Two", x=50, y=80)
        self.detector.handle_sequence(seq2_p2, page=2)
        
        self.detector.on_finish()
        questions = self.detector.get_question_list(pdf_file_name_or_path="mock_pdf.pdf")

        self.assertEqual(len(questions), 2)

        # Question 1
        q1 = questions[0]
        self.assertEqual(q1.label, "1")
        self.assertEqual(q1.level, 0)
        self.assertEqual(q1.y, 40) # Adjusted: 50 (baseline) - 10 (char_height)
        self.assertIn(1, q1.pages)
        self.assertEqual(q1.y1, 70, "Q1 y1 should be start of Q2 on page 2 (adjusted)") # Adjusted: 80 - 10


        self.assertEqual(len(q1.parts), 2, "Q1 should have 2 parts")
        
        # Part A (q1.parts[0])
        part_a = q1.parts[0]
        self.assertEqual(part_a.label, "a")
        self.assertEqual(part_a.level, 1)
        self.assertEqual(part_a.y, 70) # Adjusted: 80 - 10
        self.assertIn(1, part_a.pages)
        self.assertEqual(part_a.y1, 115, "Part A y1 should be start of Part B (adjusted)") # Adjusted: 125 - 10
        self.assertEqual(len(part_a.parts), 2, "Part A should have 2 sub-parts")

        # Sub-part i (part_a.parts[0])
        sub_i = part_a.parts[0]
        self.assertEqual(sub_i.label, "i")
        self.assertEqual(sub_i.level, 2)
        self.assertEqual(sub_i.y, 85) # Adjusted: 95 - 10
        self.assertIn(1, sub_i.pages)
        self.assertEqual(sub_i.y1, 100, "Sub-part i y1 should be start of sub-part ii (adjusted)") # Adjusted: 110 - 10
        
        # Sub-part ii (part_a.parts[1])
        sub_ii = part_a.parts[1]
        self.assertEqual(sub_ii.label, "ii")
        self.assertEqual(sub_ii.level, 2)
        self.assertEqual(sub_ii.y, 100) # Adjusted: 110 - 10
        self.assertIn(1, sub_ii.pages)
        self.assertEqual(sub_ii.y1, 115, "Sub-part ii y1 should be start of Part B (adjusted)") # Adjusted: 125 - 10

        # Part B (q1.parts[1])
        part_b = q1.parts[1]
        self.assertEqual(part_b.label, "b")
        self.assertEqual(part_b.level, 1)
        self.assertEqual(part_b.y, 115) # Adjusted: 125 - 10 (on page 1)
        self.assertIn(1, part_b.pages)
        self.assertIn(2, part_b.pages, "Part B should span to page 2")
        self.assertEqual(part_b.y1, 70, "Part B y1 should be start of Q2 on page 2 (adjusted)") # Adjusted: 80 - 10


        # Question 2
        q2 = questions[1]
        self.assertEqual(q2.label, "2")
        self.assertEqual(q2.level, 0)
        self.assertEqual(q2.y, 70) # Adjusted: 80 - 10 (on page 2)
        self.assertIn(2, q2.pages)
        self.assertEqual(q2.y1, self.page_height, "Q2 y1 should be page_height") 
        self.assertEqual(len(q2.parts), 0)


if __name__ == '__main__':
    unittest.main()
