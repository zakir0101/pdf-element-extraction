#! ./venv/bin/python

import tkinter as tk
from tkinter import ttk
import os
from tkinter import filedialog  # Though not used for file picking yet
from functools import partial  # For cleaner command binding if needed
import importlib

# Import for reloading and instantiation
from engine import pdf_engine as pdf_engine_module
from engine.pdf_engine import PdfEngine
from PIL import Image, ImageTk
import cairo  # For type hinting and direct use if necessary

"""
Advanced PDF Viewer GUI application.

This module implements a Tkinter-based GUI for viewing and interacting with PDF files.
It supports navigation by page and by extracted questions, debugging rendering of pages
and question extraction, and live reloading of its PDF processing engine.
The GUI displays PDF pages or question representations as images on a canvas.
"""


class AdvancedPDFViewer(tk.Tk):
    """
    Main application class for the Advanced PDF Viewer.

    Manages the main window, UI frames (controls, display, status bar),
    event handling (button clicks, keyboard shortcuts), and interaction
    with the PdfEngine for PDF processing and rendering.
    """

    def __init__(self, pdf_pathes):
        """
        Initializes the AdvancedPDFViewer application.

        Sets up the main window, PDF engine instance, UI frames, widgets,
        and keyboard shortcuts. Also loads the initial PDF if available.
        """
        super().__init__()
        self._photo_image_ref = (
            None  # Keep reference to PhotoImage preventing garbage collection
        )

        self.title("Advanced PDF Viewer")
        self.geometry("1024x768")

        # Initialize PDF Engine
        self.engine = (
            PdfEngine()
        )  # Initial instantiation using PdfEngine directly
        self.navigation_mode = "page"  # "page" or "question"
        self.current_page_number = 0
        self.total_pages = 0
        self.current_question_number = 0
        self.total_questions = 0
        self.questions_list = []  # To store extracted questions
        # TODO: Make PDF loading more dynamic, e.g., via a file dialog or config
        sample_pdf_paths = [
            "PDFs/9702_m23_qp_12.pdf",
            "PDFs/9702_m23_qp_22.pdf",
        ]
        sample_pdf_paths = pdf_pathes
        # Ensure the PDFs directory exists for sample paths if running from repo root
        # For now, assuming these paths are valid relative to where the script is run
        # Or that the PdfEngine handles path resolution.
        self.engine.set_files(sample_pdf_paths)

        # Create main frames
        self.display_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=2)
        self.controls_frame = ttk.Frame(self, relief=tk.GROOVE, borderwidth=2)
        self.status_bar_frame = ttk.Frame(
            self, relief=tk.GROOVE, borderwidth=2
        )

        # Layout the frames
        self.controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        self.status_bar_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        self.display_frame.pack(
            side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )

        # Display Frame setup for image rendering with scrollbars
        self.v_scrollbar = ttk.Scrollbar(
            self.display_frame, orient=tk.VERTICAL
        )
        self.h_scrollbar = ttk.Scrollbar(
            self.display_frame, orient=tk.HORIZONTAL
        )

        self.display_canvas = tk.Canvas(
            self.display_frame,
            bg="lightgray",  # Changed bg for visibility
            yscrollcommand=self.v_scrollbar.set,
            xscrollcommand=self.h_scrollbar.set,
        )

        self.v_scrollbar.config(command=self.display_canvas.yview)
        self.h_scrollbar.config(command=self.display_canvas.xview)

        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        # Important: Pack canvas AFTER scrollbars if scrollbars are outside,
        # or ensure canvas is the primary widget if scrollbars are inside its allocated space.
        # Current packing order (display_frame packs canvas and scrollbars) is fine.
        self.display_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create an image item on the canvas. This item will be updated with new page/question images.
        self.canvas_image_item = self.display_canvas.create_image(
            0, 0, anchor=tk.NW, image=None
        )

        # --- Controls Frame ---
        # PDF Navigation Buttons
        self.prev_pdf_button = ttk.Button(
            self.controls_frame,
            text="Previous PDF (Ctrl-Alt-H)",
            command=self.previous_pdf_file,
        )
        self.prev_pdf_button.pack(fill=tk.X, padx=5, pady=2)

        self.next_pdf_button = ttk.Button(
            self.controls_frame,
            text="Next PDF (Ctrl-Alt-L)",
            command=self.next_pdf_file,
        )
        self.next_pdf_button.pack(fill=tk.X, padx=5, pady=2)

        ttk.Separator(self.controls_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # Page/Item Navigation Buttons
        self.prev_item_button = ttk.Button(
            self.controls_frame,
            text="Previous Item (Ctrl-Alt-K)",
            command=self.previous_item,
        )
        self.prev_item_button.pack(fill=tk.X, padx=5, pady=2)

        self.next_item_button = ttk.Button(
            self.controls_frame,
            text="Next Item (Ctrl-Alt-J)",
            command=self.next_item,
        )
        self.next_item_button.pack(fill=tk.X, padx=5, pady=2)

        ttk.Separator(self.controls_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # Mode Switching Buttons
        self.page_mode_button = ttk.Button(
            self.controls_frame,
            text="View Pages (Ctrl+P)",
            command=self.switch_to_page_mode,
        )
        self.page_mode_button.pack(fill=tk.X, padx=5, pady=2)

        self.question_mode_button = ttk.Button(
            self.controls_frame,
            text="View Questions (Ctrl+Q)",
            command=self.switch_to_question_mode,
        )
        self.question_mode_button.pack(fill=tk.X, padx=5, pady=2)

        ttk.Separator(self.controls_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # Debugging Button
        self.debug_button = ttk.Button(
            self.controls_frame,
            text="Debug Item (Ctrl+D)",
            command=self.debug_current_item,
        )
        self.debug_button.pack(fill=tk.X, padx=5, pady=2)

        # Combined Debug (Ctrl+Shift+D) - conceptual, button might be redundant if shortcut is primary
        # For now, let's rely on the shortcut for combined_debug=True.
        # If a button is desired, it could be added here.

        ttk.Separator(self.controls_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, pady=10
        )

        # Reloading Button
        self.reload_button = ttk.Button(
            self.controls_frame,
            text="Reload Engine (Ctrl+R)",
            command=self.reload_engine_code,
        )
        self.reload_button.pack(fill=tk.X, padx=5, pady=2)

        # --- Status Bar Frame ---
        self.status_bar_text = tk.StringVar()
        self.status_bar_label = ttk.Label(
            self.status_bar_frame,
            textvariable=self.status_bar_text,
            relief=tk.SUNKEN,
            anchor=tk.W,
            wraplength=800,
            justify=tk.LEFT,
        )  # wraplength and justify for long messages
        self.status_bar_label.pack(fill=tk.X, expand=True, padx=2, pady=2)
        # Initial message set by update_status_bar in __init__ later

        # --- Keyboard Shortcuts ---
        self.bind("<Control-Alt-l>", lambda event: self.next_pdf_file())
        self.bind("<Control-Alt-h>", lambda event: self.previous_pdf_file())
        self.bind("<Control-Alt-j>", lambda event: self.next_item())
        self.bind("<Control-Alt-k>", lambda event: self.previous_item())
        self.bind("<Control-p>", self.switch_to_page_mode)
        self.bind("<Control-q>", self.switch_to_question_mode)
        self.bind(
            "<Control-d>",
            lambda event: self.debug_current_item(combined_debug=False),
        )
        self.bind(
            "<Control-Shift-D>",
            lambda event: self.debug_current_item(combined_debug=True),
        )
        self.bind("<Control-r>", self.reload_engine_code)

        # --- Initial Load ---
        self.update_status_bar(
            "Welcome! Load a PDF to begin."
        )  # Initial status
        self.update_all_button_states()  # Initial button state
        if self.engine.all_pdf_paths:
            self.next_pdf_file()  # Load the first PDF

    def update_status_bar(self, general_message: str = ""):
        """
        Updates the status bar with current file, mode, item, and a general message.

        Args:
            general_message (str, optional): A specific message to display.
                                            Defaults to "".
        """
        file_info = "File: None"
        if (
            self.engine
            and hasattr(self.engine, "pdf_path")
            and self.engine.pdf_path
        ):  # Check pdf_path exists
            file_info = f"File: {os.path.basename(self.engine.pdf_path)}"

        mode_info = f"Mode: {self.navigation_mode.capitalize()}"
        item_info = ""

        if self.navigation_mode == "page":
            if (
                self.engine.current_pdf_document and self.total_pages > 0
            ):  # Check if PDF is loaded for page info
                item_info = (
                    f"Page: {self.current_page_number}/{self.total_pages}"
                )
            else:
                item_info = "Page: N/A"
        elif self.navigation_mode == "question":
            if (
                self.engine.current_pdf_document and self.total_questions > 0
            ):  # Check if PDF is loaded for q info
                item_info = f"Question: {self.current_question_number}/{self.total_questions}"
            else:
                item_info = "Question: N/A"

        status_parts = [file_info, mode_info, item_info]
        if general_message:
            # Limit general message length if too long, or let wraplength handle it
            status_parts.append(f"Status: {general_message}")

        full_status = " | ".join(
            filter(None, status_parts)
        )  # filter(None,...) to remove empty strings if item_info is empty
        self.status_bar_text.set(full_status)
        # print(f"Status Updated: {full_status}") # For debugging status updates

    def render_current_page_or_question(self):
        """
        Renders the current page or question based on the navigation mode.

        Fetches the appropriate content (page image or question representation)
        from the PdfEngine, converts it to a displayable format, and updates
        the main canvas. Also updates the status bar.
        """
        # Method attributes like current_file_name are derived by update_status_bar or within logic.
        status_message_detail = ""
        action_description = ""  # For print logging

        # Clear any old text items from canvas, except the image item itself
        for item in self.display_canvas.find_all():
            if item != self.canvas_image_item:
                self.display_canvas.delete(item)

        # Method attributes like current_file_name are derived by update_status_bar or within logic.
        surface = None
        general_render_message = ""  # Specific message for this render action

        # Clear any old text items from canvas, except the image item itself
        for item in self.display_canvas.find_all():
            if item != self.canvas_image_item:
                self.display_canvas.delete(item)

        if (
            not self.engine.current_pdf_document
            or not self.engine.get_current_file_path()
        ):
            self.display_canvas.itemconfig(self.canvas_image_item, image=None)
            self._photo_image_ref = None
            self.display_canvas.config(scrollregion=(0, 0, 0, 0))
            self.update_status_bar("No PDF loaded.")
            self.update_all_button_states()
            return

        # Update status before attempting render, indicating action
        # self.update_status_bar(f"Rendering {self.navigation_mode}...") # This will be more specific below

        try:
            if self.navigation_mode == "page":
                if self.current_page_number > 0 and self.total_pages > 0:
                    self.update_status_bar(
                        f"Rendering Page {self.current_page_number}/{self.total_pages}..."
                    )
                    surface = self.engine.render_pdf_page(
                        self.current_page_number, debug=0
                    )
                    general_render_message = (
                        "Page displayed."
                        if surface
                        else "Failed to render page."
                    )
                else:
                    general_render_message = (
                        "No page selected or PDF has no pages."
                    )
            elif self.navigation_mode == "question":
                if (
                    self.current_question_number > 0
                    and self.total_questions > 0
                    and self.questions_list
                ):
                    self.update_status_bar(
                        f"Rendering Question {self.current_question_number}/{self.total_questions}..."
                    )
                    surface = self.engine.render_a_question(
                        self.current_question_number
                    )

                    if (
                        surface is None
                        and self.current_question_number - 1
                        < len(self.questions_list)
                    ):  # Fallback
                        current_q = self.questions_list[
                            self.current_question_number - 1
                        ]
                        if current_q.pages:
                            page_to_render = current_q.pages[0]
                            self.update_status_bar(
                                f"Fallback: Rendering Page {page_to_render} for Q{self.current_question_number}."
                            )
                            surface = self.engine.render_pdf_page(
                                page_to_render, debug=0
                            )
                    general_render_message = (
                        "Question displayed."
                        if surface
                        else "Failed to render question."
                    )
                    if surface is None:
                        general_render_message += (
                            " (Not available/Fallback failed)"
                        )
                else:
                    general_render_message = (
                        "No question selected or no questions available."
                    )

            print(general_render_message)  # Print what was attempted/result

            if surface:
                self._photo_image_ref = (
                    self.convert_cairo_surface_to_photoimage(surface)
                )
                self.display_canvas.itemconfig(
                    self.canvas_image_item, image=self._photo_image_ref
                )
                self.display_canvas.coords(self.canvas_image_item, 0, 0)
                self.display_canvas.config(
                    scrollregion=self.display_canvas.bbox(
                        self.canvas_image_item
                    )
                )
            else:
                self.display_canvas.itemconfig(
                    self.canvas_image_item, image=None
                )
                self._photo_image_ref = None
                self.display_canvas.config(scrollregion=(0, 0, 0, 0))

            self.update_status_bar(
                general_render_message
            )  # Final status update

        except Exception as e:
            error_msg = f"Error rendering {self.navigation_mode}: {e}"
            print(error_msg)
            self.update_status_bar(error_msg)
            self.display_canvas.itemconfig(self.canvas_image_item, image=None)
            self._photo_image_ref = None
            self.display_canvas.config(scrollregion=(0, 0, 0, 0))

        self.update_all_button_states()

    def convert_cairo_surface_to_photoimage(
        self, surface: cairo.ImageSurface
    ) -> ImageTk.PhotoImage | None:
        """
        Converts a Cairo ImageSurface to a Tkinter PhotoImage.

        Args:
            surface (cairo.ImageSurface): The Cairo surface to convert.

        Returns:
            ImageTk.PhotoImage | None: The converted PhotoImage, or None if conversion fails
                                      or the input surface is None. Returns a placeholder error
                                      image if conversion encounters issues.
        """
        if surface is None:
            print(
                "convert_cairo_surface_to_photoimage: Received None surface."
            )
            return None

        width = surface.get_width()
        height = surface.get_height()
        stride = surface.get_stride()
        cairo_format = surface.get_format()

        try:
            data_buffer = (
                surface.get_data()
            )  # Get data after checking surface is not None
        except (
            Exception
        ) as e:  # Underlying surface might be bad (e.g. after PDF error)
            print(f"Error getting data from Cairo surface: {e}")
            pil_image = Image.new(
                "RGB", (max(1, width), max(1, height)), color="purple"
            )  # Use max(1,...) for 0-size
            from PIL import ImageDraw  # Local import for error case

            temp_draw = ImageDraw.Draw(pil_image)
            temp_draw.text((10, 10), f"Surface Data Error: {e}", fill="white")
            return ImageTk.PhotoImage(pil_image)

        try:
            if cairo_format == cairo.FORMAT_ARGB32:
                pil_image = Image.frombytes(
                    "RGBA",
                    (width, height),
                    data_buffer.tobytes(),
                    "raw",
                    "BGRA",
                    stride,
                )
            elif cairo_format == cairo.FORMAT_RGB24:
                pil_image = Image.frombytes(
                    "RGB",
                    (width, height),
                    data_buffer.tobytes(),
                    "raw",
                    "BGRX",
                    stride,
                )
            else:
                error_msg = f"Unsupported Cairo format: {cairo_format}."
                print(error_msg)
                pil_image = Image.new("RGB", (width, height), color="red")
                from PIL import ImageDraw  # Local import for error case

                temp_draw = ImageDraw.Draw(pil_image)
                temp_draw.text((10, 10), error_msg, fill="white")

            return ImageTk.PhotoImage(pil_image)
        except Exception as e:
            error_msg = f"Error converting Cairo surface to PhotoImage: {e}"
            print(error_msg)
            pil_image = Image.new(
                "RGB", (max(1, width), max(1, height)), color="orange"
            )
            from PIL import ImageDraw  # Local import for error case

            temp_draw = ImageDraw.Draw(pil_image)
            temp_draw.text((10, 10), error_msg, fill="black")
            return ImageTk.PhotoImage(pil_image)

    def debug_current_item(self, event=None, combined_debug=False):
        """
        Performs debug operations on the current item (page or questions).

        Args:
            event (tk.Event, optional): Event that triggered the call (e.g., keyboard shortcut).
                                       Defaults to None.
            combined_debug (bool, optional): If True, performs combined debug (extract questions
                                             then render a page with debug flags). Otherwise,
                                             performs standard debug based on current mode.
                                             Defaults to False.
        """
        if not self.engine.current_pdf_document:
            self.update_status_bar("No PDF loaded to debug.")
            self.display_canvas.itemconfig(self.canvas_image_item, image=None)
            self._photo_image_ref = None
            self.display_canvas.config(scrollregion=(0, 0, 0, 0))
            return

        surface = None
        general_debug_message = ""

        try:
            if not combined_debug:
                if self.navigation_mode == "page":
                    if self.current_page_number > 0:
                        self.update_status_bar(
                            f"Debugging Page {self.current_page_number}..."
                        )
                        surface = self.engine.render_pdf_page(
                            self.current_page_number, debug=self.engine.M_DEBUG
                        )
                        general_debug_message = (
                            f"Debugged Page {self.current_page_number}."
                        )
                    else:
                        general_debug_message = "No page selected to debug."
                elif self.navigation_mode == "question":
                    self.update_status_bar(
                        "Debugging Questions (extraction)..."
                    )
                    self.questions_list = (
                        self.engine.extract_questions_from_pdf(
                            debug=self.engine.M_DEBUG
                        )
                    )
                    self.total_questions = (
                        len(self.questions_list) if self.questions_list else 0
                    )
                    if (
                        self.current_question_number > self.total_questions
                        or (
                            self.current_question_number == 0
                            and self.total_questions > 0
                        )
                    ):
                        self.current_question_number = (
                            1 if self.total_questions > 0 else 0
                        )

                    general_debug_message = "Debugged Questions (extraction)."
                    if (
                        self.current_question_number > 0
                        and self.total_questions > 0
                    ):
                        general_debug_message += (
                            f" Current Q{self.current_question_number}."
                        )

                    # Refresh main display based on (potentially) new question data.
                    # This call will also handle its own status update regarding rendering.
                    self.render_current_page_or_question()
                    # Then, set the specific debug general message.
                    self.update_status_bar(general_debug_message)
                    self.update_all_button_states()
                    return  # Return early as render_current_page_or_question handles display & its status
            else:  # Combined Debug
                self.update_status_bar(
                    "Combined Debug: Extracting questions..."
                )
                self.questions_list = self.engine.extract_questions_from_pdf(
                    debug=self.engine.M_DEBUG
                )
                self.total_questions = (
                    len(self.questions_list) if self.questions_list else 0
                )
                if self.current_question_number > self.total_questions or (
                    self.current_question_number == 0
                    and self.total_questions > 0
                ):
                    self.current_question_number = (
                        1 if self.total_questions > 0 else 0
                    )

                page_to_debug = 1
                if (
                    self.navigation_mode == "page"
                    and self.current_page_number > 0
                ):
                    page_to_debug = self.current_page_number
                elif (
                    self.navigation_mode == "question"
                    and self.current_question_number > 0
                    and self.questions_list
                ):
                    try:
                        current_q = self.questions_list[
                            self.current_question_number - 1
                        ]
                        if current_q.pages:
                            page_to_debug = current_q.pages[0]
                        else:
                            print(
                                f"Warning: Q{self.current_question_number} has no 'pages'. Defaulting page 1 for debug."
                            )
                    except IndexError:
                        print(
                            f"Error: Q_idx {self.current_question_number} out of bounds. Defaulting page 1 for debug."
                        )
                    except AttributeError:
                        print(
                            f"Error: Question object missing 'pages'. Defaulting page 1 for debug."
                        )

                self.update_status_bar(
                    f"Combined Debug: Rendering page {page_to_debug}..."
                )
                surface = self.engine.render_pdf_page(
                    page_to_debug, debug=self.engine.M_DEBUG
                )
                general_debug_message = f"Combined Debug: Questions extracted & Page {page_to_debug} debugged."

            # Common surface handling for non-question-extraction debug or combined page debug
            if surface:
                self._photo_image_ref = (
                    self.convert_cairo_surface_to_photoimage(surface)
                )
                self.display_canvas.itemconfig(
                    self.canvas_image_item, image=self._photo_image_ref
                )
                self.display_canvas.coords(self.canvas_image_item, 0, 0)
                self.display_canvas.config(
                    scrollregion=self.display_canvas.bbox(
                        self.canvas_image_item
                    )
                )
            elif not (
                not combined_debug and self.navigation_mode == "question"
            ):
                self.display_canvas.itemconfig(
                    self.canvas_image_item, image=None
                )
                self._photo_image_ref = None
                self.display_canvas.config(scrollregion=(0, 0, 0, 0))

            # If combined debug, after potentially displaying the debugged page surface,
            # refresh the main display to be consistent with the current navigation mode and item.
            # The debugged page surface takes precedence for one-time view if generated.
            if combined_debug:
                if (
                    not surface
                ):  # If combined debug didn't produce a direct page surface to display.
                    self.render_current_page_or_question()  # This will set its own status.
                # The general_debug_message for combined debug will be set as the final status.

            self.update_status_bar(general_debug_message)

        except Exception as e:
            error_msg = f"Error during debug: {e}"
            print(error_msg)
            self.update_status_bar(error_msg)
            self.display_canvas.itemconfig(self.canvas_image_item, image=None)
            self._photo_image_ref = None
            self.display_canvas.config(scrollregion=(0, 0, 0, 0))

        self.update_all_button_states()

    def reload_engine_code(self, event=None):
        """
        Reloads the PdfEngine module and re-initializes the engine instance.

        Attempts to preserve and restore the current viewing state (PDF file,
        page/question number, mode) after the reload.

        Args:
            event (tk.Event, optional): Event that triggered the call. Defaults to None.
        """
        print("Attempting to reload PDF Engine module...")
        current_pdf_path = None
        current_page = self.current_page_number
        current_question = self.current_question_number
        current_mode = self.navigation_mode
        all_pdf_paths = list(self.engine.all_pdf_paths)  # Make a copy
        current_pdf_idx = self.engine.current_pdf_index
        original_scaling = (
            self.engine.scaling
        )  # Assuming scaling is an attribute

        if (
            self.engine.current_pdf_document
            and self.engine.get_current_file_path()
        ):
            current_pdf_path = self.engine.get_current_file_path()
            # current_pdf_name = os.path.basename(current_pdf_path) # Not strictly needed for restore

        try:
            self.update_status_bar("Reloading engine module...")
            importlib.reload(pdf_engine_module)
            print("PDF Engine module reloaded.")

            self.update_status_bar("Re-initializing PDF Engine...")
            self.engine = pdf_engine_module.PdfEngine(scaling=original_scaling)
            print("PDF Engine re-initialized.")

            self.update_status_bar("Engine re-initialized. Restoring state...")
            # Reset GUI state that depends on engine instance details not yet restored
            self.total_pages = 0
            self.current_page_number = 0
            self.total_questions = 0
            self.current_question_number = 0
            self.questions_list = []

            if all_pdf_paths:
                self.engine.set_files(all_pdf_paths)  # Restore file list

                if (
                    current_pdf_path and current_pdf_idx != -1
                ):  # Check if a PDF was actually loaded
                    # Try to restore to the previously active PDF
                    # process_next_pdf_file increments index *before* loading.
                    # So, to load current_pdf_idx, we need to set index to current_pdf_idx - 1.
                    self.engine.current_pdf_index = current_pdf_idx - 1

                    if (
                        self.engine.proccess_next_pdf_file()
                    ):  # This should load the PDF at current_pdf_idx
                        print(
                            f"Successfully reloaded and processed: {self.engine.get_current_file_path()}"
                        )
                        self.total_pages = (
                            self.engine.get_num_pages()
                            if self.engine.current_pdf_document
                            else 0
                        )

                        if current_mode == "page":
                            self.navigation_mode = "page"
                            self.current_page_number = (
                                min(current_page, self.total_pages)
                                if self.total_pages > 0
                                else 0
                            )
                            if (
                                self.current_page_number == 0
                                and self.total_pages > 0
                            ):
                                self.current_page_number = 1

                        elif current_mode == "question":
                            # switch_to_question_mode will try to extract questions
                            self.switch_to_question_mode()  # This sets nav_mode and extracts questions
                            self.current_question_number = (
                                min(current_question, self.total_questions)
                                if self.total_questions > 0
                                else 0
                            )
                            if (
                                self.current_question_number == 0
                                and self.total_questions > 0
                            ):
                                self.current_question_number = 1

                        # render_current_page_or_question will call update_status_bar with item details.
                        self.render_current_page_or_question()
                        self.update_status_bar(
                            f"Engine reloaded. Restored state for {os.path.basename(current_pdf_path)}."
                        )
                    else:
                        self.render_current_page_or_question()
                        self.update_status_bar(
                            "Engine reloaded. Could not restore previous PDF."
                        )
                else:
                    self.render_current_page_or_question()
                    self.update_status_bar(
                        "Engine reloaded. No active PDF to restore. File list restored if any."
                    )
            else:
                self.render_current_page_or_question()
                self.update_status_bar(
                    "Engine reloaded. No previous PDF list to restore."
                )

        except Exception as e:
            error_message = f"Error reloading engine: {e}"
            print(error_message)  # Keep console print for dev
            self.update_status_bar(f"Critical error reloading engine: {e}")
            # Potentially, the engine is in a bad state. Could try to revert to a new clean instance.
            # For now, just report error. User might need to restart if it's critical.

        self.update_all_button_states()

    def next_pdf_file(self):
        """
        Loads and displays the next PDF file in the list.
        Resets view to page mode and first page. Updates status and button states.
        """
        if self.engine.proccess_next_pdf_file():
            self.navigation_mode = "page"  # Default to page mode on new PDF
            self.total_pages = (
                self.engine.get_num_pages()
                if self.engine.current_pdf_document
                else 0
            )
            self.current_page_number = 1 if self.total_pages > 0 else 0
            self.total_questions = 0  # Reset questions for new PDF
            self.current_question_number = 0
            self.questions_list = []
            self.render_current_page_or_question()
        else:
            self.total_pages = 0
            self.current_page_number = 0
            self.total_questions = 0
            self.current_question_number = 0
            self.render_current_page_or_question()  # Will show "No PDF" or similar & update status
            self.update_status_bar(
                "End of PDF list."
            )  # Explicitly set general message
        self.update_all_button_states()

    def previous_pdf_file(self):
        """
        Loads and displays the previous PDF file in the list.
        Resets view to page mode and first page. Updates status and button states.
        """
        if not self.engine.all_pdf_paths:
            self.render_current_page_or_question()  # Shows "No PDF"
            self.update_status_bar("No PDF files loaded.")
            self.update_all_button_states()
            return

        if self.engine.current_pdf_index > 0:
            self.engine.current_pdf_index -= 1
            success = self.engine.initialize_file(
                self.engine.all_pdf_paths[self.engine.current_pdf_index]
            )
            self.navigation_mode = "page"
            if success:
                self.total_pages = (
                    self.engine.get_num_pages()
                    if self.engine.current_pdf_document
                    else 0
                )
                self.current_page_number = 1 if self.total_pages > 0 else 0
                # Status will be updated by render_current_page_or_question
            else:
                self.total_pages = 0
                self.current_page_number = 0
                self.engine.current_pdf_document = None
                # Status will be updated by render_current_page_or_question to show no PDF
            self.total_questions = 0
            self.current_question_number = 0
            self.questions_list = []
            self.render_current_page_or_question()
        else:
            # Already at the beginning, no change in PDF, but refresh status
            self.render_current_page_or_question()
            self.update_status_bar("At the beginning of PDF list.")

        self.update_all_button_states()

    def switch_to_page_mode(self, event=None):
        """
        Switches the navigation mode to "page".
        Updates display to show the current page. Refreshes status and button states.

        Args:
            event (tk.Event, optional): Event that triggered the call. Defaults to None.
        """
        if self.navigation_mode == "page":
            self.update_status_bar("Already in Page Mode.")
            return
        print("Switching to Page Mode")
        self.navigation_mode = "page"
        if not self.engine.current_pdf_document or self.total_pages == 0:
            self.current_page_number = 0
        elif self.current_page_number == 0 and self.total_pages > 0:
            self.current_page_number = 1

        # render_current_page_or_question will call update_status_bar with item details
        self.render_current_page_or_question()
        self.update_status_bar(
            "Switched to Page Mode."
        )  # General confirmation
        self.update_all_button_states()

    def switch_to_question_mode(self, event=None):
        """
        Switches the navigation mode to "question".
        Extracts questions from the current PDF if not already done.
        Updates display to show the current question. Refreshes status and button states.

        Args:
            event (tk.Event, optional): Event that triggered the call. Defaults to None.
        """
        if self.navigation_mode == "question":
            self.update_status_bar("Already in Question Mode.")
            return
        print("Switching to Question Mode")
        self.navigation_mode = "question"

        if self.engine.current_pdf_document:
            try:
                self.update_status_bar("Extracting questions...")
                self.questions_list = self.engine.extract_questions_from_pdf()
                self.total_questions = (
                    len(self.questions_list) if self.questions_list else 0
                )
                self.current_question_number = (
                    1 if self.total_questions > 0 else 0
                )
                if self.total_questions == 0:
                    print("No questions found in the PDF.")
                    self.update_status_bar("No questions found in this PDF.")
                else:
                    # render_current_page_or_question will show item details
                    self.update_status_bar(
                        f"Switched to Question Mode. {self.total_questions} questions found."
                    )
            except Exception as e:
                error_msg = f"Error extracting questions: {e}"
                print(error_msg)
                self.update_status_bar(error_msg)
                self.questions_list = []
                self.total_questions = 0
                self.current_question_number = 0
        else:
            self.questions_list = []
            self.total_questions = 0
            self.current_question_number = 0
            self.update_status_bar("No PDF loaded to extract questions from.")

        self.render_current_page_or_question()
        self.update_all_button_states()

    def next_item(self):
        """
        Navigates to the next item (page or question) based on the current mode.
        Updates display, status, and button states.
        """
        if not self.engine.current_pdf_document:
            self.update_status_bar("No PDF loaded to navigate items.")
            return

        changed = False
        if self.navigation_mode == "page":
            if self.current_page_number < self.total_pages:
                self.current_page_number += 1
                changed = True
        elif self.navigation_mode == "question":
            if self.current_question_number < self.total_questions:
                self.current_question_number += 1
                changed = True

        if changed:
            self.render_current_page_or_question()  # Handles status update for item change
        else:
            self.update_status_bar(
                f"Already at the last {self.navigation_mode}."
            )
        self.update_all_button_states()

    def previous_item(self):
        """
        Navigates to the previous item (page or question) based on the current mode.
        Updates display, status, and button states.
        """
        if not self.engine.current_pdf_document:
            self.update_status_bar("No PDF loaded to navigate items.")
            return

        changed = False
        if self.navigation_mode == "page":
            if self.current_page_number > 1:
                self.current_page_number -= 1
                changed = True
        elif self.navigation_mode == "question":
            if self.current_question_number > 1:
                self.current_question_number -= 1
                changed = True

        if changed:
            self.render_current_page_or_question()  # Handles status update for item change
        else:
            self.update_status_bar(
                f"Already at the first {self.navigation_mode}."
            )
        self.update_all_button_states()

    def update_all_button_states(self):
        """
        Updates the enabled/disabled state of all navigation and mode buttons
        based on the current application state (loaded PDF, current item, mode, etc.).
        """
        num_files = len(self.engine.all_pdf_paths)
        current_pdf_idx = self.engine.current_pdf_index
        pdf_loaded = self.engine.current_pdf_document is not None

        # PDF Navigation Buttons
        self.next_pdf_button.config(
            state=(
                tk.NORMAL
                if num_files > 0 and current_pdf_idx < num_files - 1
                else tk.DISABLED
            )
        )
        self.prev_pdf_button.config(
            state=(
                tk.NORMAL
                if num_files > 0 and current_pdf_idx > 0
                else tk.DISABLED
            )
        )

        # Mode Switching Buttons
        self.page_mode_button.config(
            state=tk.DISABLED if self.navigation_mode == "page" else tk.NORMAL
        )
        self.question_mode_button.config(
            state=(
                tk.DISABLED
                if self.navigation_mode == "question"
                else tk.NORMAL
            )
        )
        if not pdf_loaded:  # Disable mode switching if no PDF
            self.page_mode_button.config(state=tk.DISABLED)
            self.question_mode_button.config(state=tk.DISABLED)

        # Item Navigation Buttons
        if pdf_loaded:
            if self.navigation_mode == "page":
                self.next_item_button.config(
                    state=(
                        tk.NORMAL
                        if self.current_page_number < self.total_pages
                        else tk.DISABLED
                    )
                )
                self.prev_item_button.config(
                    state=(
                        tk.NORMAL
                        if self.current_page_number > 1
                        else tk.DISABLED
                    )
                )
            elif self.navigation_mode == "question":
                self.next_item_button.config(
                    state=(
                        tk.NORMAL
                        if self.current_question_number < self.total_questions
                        else tk.DISABLED
                    )
                )
                self.prev_item_button.config(
                    state=(
                        tk.NORMAL
                        if self.current_question_number > 1
                        else tk.DISABLED
                    )
                )
            else:  # Should not happen
                self.next_item_button.config(state=tk.DISABLED)
                self.prev_item_button.config(state=tk.DISABLED)
        else:  # No PDF loaded
            self.next_item_button.config(state=tk.DISABLED)
            self.prev_item_button.config(state=tk.DISABLED)


if __name__ == "__main__":
    # This assumes that 'engine' and 'PDFs' are in the right place relative to 'gui'
    # If running advanced_pdf_gui.py directly from the 'gui' folder,
    # Python's import system might need adjustment for 'engine.pdf_engine'
    # e.g. by adding the parent directory to sys.path.
    # For now, we assume the execution context is the root of the repository.
    app = AdvancedPDFViewer()
    app.mainloop()
