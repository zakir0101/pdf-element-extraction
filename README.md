project goal was to process raw PDF fils containing exams (IGCSE) and identify elements object in them like : questions , diagrams, tables, latex-equations ..

first step was to create a rendering engine to verify that we can capture PDF commands and parse them correctly.

currently the rendering engine is able to render the pdf file ,but it does not use the same embeded font in the target pdf, work has been done to enable this feature but its not complete yet , and need fixing some minor issues [ per_font.py and pdf_renderer.py].


