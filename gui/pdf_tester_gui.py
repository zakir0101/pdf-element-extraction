import tkinter as tk
import tkinter
from tkinter import font as tkFont
from PIL import Image, ImageTk
import cairo  # For the dummy surface creation in example usage


# --- Global state for the GUI ---
# This is often better managed in a class, but for a single script
# with specific API functions, globals can be acceptable if handled carefully.
_gui_root = None
_image_label = None
_user_response_var = None  # To hold True/False/None, used with wait_variable

STATE_WATING = "WATING"
STATE_CORRECT = "CORRECT"
STATE_WRONG = "WRONG"
STATE_DONE = "DONE"


# --- Internal GUI Helper Functions ---
def _on_yes_button(event=None):
    global _user_response_var
    if _user_response_var:
        _user_response_var.set(STATE_CORRECT)


def _on_no_button(event=None):
    global _user_response_var
    if _user_response_var:
        _user_response_var.set(STATE_WRONG)


def _on_quit_button(event=None):
    global _user_response_var
    if _user_response_var:
        _user_response_var.set(STATE_DONE)


def _on_window_close():
    """Handles the window close button ('X')."""
    global _gui_root, _user_response_var
    if _user_response_var:
        _user_response_var.set(
            STATE_DONE
        )  # Special value to indicate window closed
    if _gui_root:
        _gui_root.destroy()  # Ensure the main loop can terminate if wait_variable is active
        _gui_root = None


# --- Exported API Functions ---

img_frame_width, img_frame_height = 0, 0
_canvas = None  # Will hold the tk.Canvas widget
_canvas_image_item = None  # Will store the ID of the image on the canvas
_photo_image_ref = None  # CRITICAL: To prevent PhotoImage garbage collection


def end():
    pass
    # global _gui_root, _user_response_var
    # _gui_root.destroy()
    # _gui_root = None


def start(width, height):
    """
    Opens the GUI window with the specified dimensions.

    Args:
        width (int): The initial width of the GUI window.
        height (int): The initial height of the GUI window.
    """
    global _gui_root, _image_label, _user_response_var

    if _gui_root and _gui_root.winfo_exists():
        _gui_root.lift()  # Bring to front if already exists
        return

    _gui_root = tk.Tk()
    pad = 50
    if width <= 0:
        width = _gui_root.winfo_screenwidth() - pad
    if height <= 0:
        height = _gui_root.winfo_screenheight() - pad

    _gui_root.title("PDF Page Rendering Test")
    _gui_root.geometry(f"{width}x{height}")
    _gui_root.protocol(
        "WM_DELETE_WINDOW", _on_window_close
    )  # Handle 'X' button

    # --- Styling ---
    default_font = tkFont.nametofont("TkDefaultFont")
    default_font.configure(size=11)
    _gui_root.option_add("*Font", default_font)

    button_font = tkFont.Font(family="Helvetica", size=12, weight="bold")
    label_font = tkFont.Font(family="Helvetica", size=14)

    # --- Layout ---
    # Main frame to hold all content
    main_frame = tk.Frame(_gui_root, padx=15, pady=5)
    main_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
    control_frame = tk.Frame(_gui_root, padx=15, pady=15)
    control_frame.pack(fill=tk.Y, expand=False, side=tk.LEFT)

    # image_frame = tk.Frame(
    #     main_frame,
    #     relief=tk.SUNKEN,
    #     borderwidth=1,
    #     bg="lightgrey",
    # )
    # image_frame.pack(fill=tk.BOTH, expand=True, pady=10)
    # _image_label = tk.Label(
    #     image_frame, bg="lightgrey"
    # )
    # _image_label.pack(fill=tk.BOTH, expand=True)  # Image will fill this label

    # --- Scrollable Image Area ---
    # Frame to hold canvas and scrollbars
    image_container_frame = tk.Frame(
        main_frame, relief=tk.SUNKEN, borderwidth=1
    )
    # This frame takes the place of your old 'image_frame' in the layout
    image_container_frame.pack(
        side=tk.TOP, fill=tk.BOTH, expand=True, pady=5
    )  # pady adjusted slightly

    global _canvas, _canvas_image_item  # Ensure we're assigning to globals

    _canvas = tk.Canvas(image_container_frame, bg="lightgrey")

    # Create scrollbars
    v_scrollbar = tk.Scrollbar(
        image_container_frame, orient=tk.VERTICAL, command=_canvas.yview
    )
    h_scrollbar = tk.Scrollbar(
        image_container_frame, orient=tk.HORIZONTAL, command=_canvas.xview
    )
    _canvas.configure(
        yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set
    )

    # Pack scrollbars and canvas within image_container_frame
    # Order matters for how they appear
    v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
    _canvas.pack(
        side=tk.LEFT, fill=tk.BOTH, expand=True
    )  # Canvas takes remaining space

    # Create an image item on the canvas. We'll update its 'image' option later.
    # (0,0) is the top-left corner of the canvas, tk.NW means anchor the image by its North-West (top-left) corner.
    _canvas_image_item = _canvas.create_image(0, 0, anchor=tk.NW, image=None)
    # --- End Scrollable Image Area ---

    # global img_frame_width, img_frame_height
    # img_frame_width = width
    # img_frame_height = height

    # Feedback Buttons Area

    question_label = tk.Label(
        control_frame, text="Is this page rendered correctly?", font=label_font
    )
    question_label.pack(pady=(0, 15))  # Padding: (top, bottom)
    button_frame = tk.Frame(control_frame)
    button_frame.pack(
        pady=(15, 0),
    )

    button_frame2 = tk.Frame(control_frame)
    button_frame2.pack(
        pady=(15, 0),
    )
    yes_button = tk.Button(
        button_frame,
        text="Yes (Ctrl+Y)",
        command=_on_yes_button,
        bg="#4CAF50",
        fg="white",
        font=button_font,
        width=12,
        relief=tk.RAISED,
        borderwidth=2,
    )
    yes_button.pack(side=tk.LEFT, padx=10)

    no_button = tk.Button(
        button_frame,
        text="No (Ctrl+N)",
        command=_on_no_button,
        bg="#F44336",
        fg="white",
        font=button_font,
        width=12,
        relief=tk.RAISED,
        borderwidth=2,
    )
    no_button.pack(side=tk.LEFT, padx=10)

    q_button = tk.Button(
        button_frame2,
        text="Quit (Ctrl+q)",
        command=_on_quit_button,
        bg="#4CAF50",
        fg="white",
        font=button_font,
        width=20,
        relief=tk.RAISED,
        borderwidth=2,
    )
    q_button.pack(side=tk.LEFT, padx=10)

    # Key bindings
    _gui_root.bind_all("<Control-z>", _on_yes_button)
    _gui_root.bind_all(
        "<Control-Z>", _on_yes_button
    )  # For Shift+Ctrl+Y if needed
    _gui_root.bind_all("<Control-n>", _on_no_button)
    _gui_root.bind_all("<Control-N>", _on_no_button)
    _gui_root.bind_all("<Control-q>", lambda x: _on_window_close())
    _gui_root.bind_all("<Control-Q>", lambda x: _on_window_close())

    # Initialize response variable for show_page
    _user_response_var = tk.StringVar(
        _gui_root
    )  # Can also store strings if needed for 'closed'
    _user_response_var.set(STATE_WATING)  # Initial state: no response yet

    _gui_root.update()  # Process events to draw the window


def show_page(cairo_image_surface: cairo.ImageSurface, ratio: float):
    """
    Displays a single PDF page (from a Cairo ImageSurface) and waits for user feedback.

    Args:
        cairo_image_surface (cairo.ImageSurface): The Cairo surface containing the rendered page.
                                                 Assumed to be cairo.FORMAT_ARGB32 or cairo.FORMAT_RGB24.

    Returns:
        bool or None: True if user clicked "Yes", False if "No".
                      Returns None if the window was closed by the user before feedback.
    """
    global _gui_root, _user_response_var

    if not _gui_root or not _gui_root.winfo_exists():
        print("Error: GUI not started or has been closed. Call start() first.")
        return None

    # Get data from Cairo surface
    surface_format = cairo_image_surface.get_format()
    width = cairo_image_surface.get_width()
    height = cairo_image_surface.get_height()
    stride = cairo_image_surface.get_stride()

    # Ensure data is flushed from Cairo's internal buffers to the surface's memory
    cairo_image_surface.flush()

    # Get raw pixel data. For ImageSurface, get_data() returns a memoryview/buffer.
    image_data_buffer = cairo_image_surface.get_data()

    # Create PIL Image from the raw data
    pil_image = None
    if surface_format == cairo.FORMAT_ARGB32:
        # ARGB32 in Cairo is often BGRA in memory on little-endian systems (like x86)
        # Pillow's "RGBA" mode expects data in R,G,B,A order.
        # "raw" mode with "BGRA" tells Pillow the byte order of the input.
        pil_image = Image.frombytes(
            "RGBA",
            (width, height),
            image_data_buffer.tobytes(),
            "raw",
            "BGRA",
            stride,
        )
    elif surface_format == cairo.FORMAT_RGB24:
        # RGB24 in Cairo is often BGRX or XBGR (padded to 32-bit) or BGR (if stride matches width*3)
        # This can be tricky. Let's assume it's BGR tightly packed or BGRX.
        # If stride is width * 4, it's likely BGRX (or similar).
        # If stride is width * 3, it's likely BGR.
        if stride == width * 3:
            pil_image = Image.frombytes(
                "RGB",
                (width, height),
                image_data_buffer.tobytes(),
                "raw",
                "BGR",
                stride,
            )
        elif (
            stride >= width * 4
        ):  # Assuming BGRX, common for cairo.FORMAT_RGB24
            pil_image = Image.frombytes(
                "RGB",
                (width, height),
                image_data_buffer.tobytes(),
                "raw",
                "BGRX",
                stride,
            )
        else:
            print(
                f"Warning: Unsupported RGB24 stride ({stride}) for width ({width}). Image might be incorrect."
            )
            # Fallback: try to create an empty image to avoid crashing
            pil_image = Image.new("RGB", (width, height), "purple")

    else:
        print(f"Unsupported Cairo surface format: {surface_format}")
        # Create a placeholder image indicating an error
        pil_image = Image.new("RGB", (width, height), "red")
        draw = ImageDraw.Draw(pil_image)
        draw.text((10, 10), "Unsupported Format", fill="white")

    # Convert PIL Image to Tkinter PhotoImage
    # Keep a reference to photo_image to prevent garbage collection!

    global img_copy, rel_scale

    # rel_scale = pil_image.width / pil_image.height
    rel_scale = ratio
    img_copy = pil_image.copy()

    # f = 2
    # scale_x = img_frame_width / pil_image.width * f
    # scale_y = img_frame_height / pil_image.height * f
    # print("scaling factors", scale_x, scale_y)
    # resized_image = pil_image.resize(
    #     (int(scale_x * img_frame_width), int(scale_x * img_frame_height))
    # )

    global _photo_image_ref, _canvas, _canvas_image_item  # Ensure access to globals

    width = int(_canvas.winfo_height() * rel_scale)
    height = _canvas.winfo_height()

    pil_image = img_copy.resize((width, height))

    # Convert PIL Image to Tkinter PhotoImage and STORE THE REFERENCE
    _photo_image_ref = ImageTk.PhotoImage(pil_image)

    # Update the image item ON THE CANVAS
    _canvas.itemconfig(_canvas_image_item, image=_photo_image_ref)

    # Update the canvas's scrollable region to match the new image's dimensions
    # This is crucial for the scrollbars to work correctly.
    # 'width' and 'height' here are from the cairo_image_surface.get_width/height()
    _canvas.config(scrollregion=(0, 0, width, height))

    # Optional: Reset scroll position to the top-left for each new page
    _canvas.xview_moveto(0)
    _canvas.yview_moveto(0)

    _canvas.bind("<Configure>", _resize_image)
    # _image_label.pack(fill=tk.BOTH, expand=True)

    # Reset response variable and wait for user input
    _user_response_var.set(STATE_WATING)  # Sentinel for "no response yet"
    _gui_root.deiconify()  # Ensure window is visible if it was iconified
    _gui_root.lift()  # Bring to front
    _gui_root.focus_force()  # Try to grab focus

    # This is the blocking part: it waits until _user_response_var is changed
    # by a button press or window close.
    _gui_root.wait_variable(_user_response_var)

    response_value = _user_response_var.get()

    # if isinstance(response_value, str) and response_value == STATE_DONE:
    #     return None  # Window was closed

    return (
        response_value  # Convert Tkinter BooleanVar's 0/1 to Python False/True
    )


def _resize_image(event: tk.Event):
    global img_copy, rel_scale, _canvas, _photo_image_ref
    try:
        new_width = int(event.height * rel_scale)
        new_height = event.height
        print(f"new dim ({new_width},{new_height} )")
        image = img_copy.resize((new_width, new_height))
        _photo_image_ref = ImageTk.PhotoImage(image)
        _canvas.itemconfig(_canvas_image_item, image=_photo_image_ref)
        _canvas.config(scrollregion=(0, 0, new_width, new_height))

    except Exception as e:
        print(e)
        raise Exception(e)


def close_gui():
    """Closes the GUI window if it's open."""
    global _gui_root
    if _gui_root and _gui_root.winfo_exists():
        _gui_root.destroy()
    _gui_root = None


# --- Example Usage (can be in a separate file or below for testing) ---
if __name__ == "__main__":
    import time
    from PIL import (
        ImageDraw,
    )  # For drawing on the dummy PIL image if cairo format is bad

    # Dummy function to create a Cairo ImageSurface (simulating your PDF engine)
    def create_dummy_cairo_surface(width, height, page_number):
        # Using ARGB32 as it's common and well-supported for transparency
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)

        # Fill background
        if page_number % 2 == 0:
            ctx.set_source_rgba(0.9, 0.9, 0.7, 1)  # Light yellowish
        else:
            ctx.set_source_rgba(0.7, 0.9, 0.9, 1)  # Light cyanish
        ctx.paint()

        # Draw some text
        ctx.select_font_face(
            "Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        ctx.set_font_size(40)
        text = f"Page {page_number}"
        xbearing, ybearing, text_width, text_height, _, _ = ctx.text_extents(
            text
        )

        ctx.set_source_rgb(0.1, 0.1, 0.1)  # Dark text
        ctx.move_to(
            width / 2 - (xbearing + text_width / 2),
            height / 2 - (ybearing + text_height / 2),
        )
        ctx.show_text(text)

        # Draw a border
        ctx.set_source_rgb(0.3, 0.3, 0.3)
        ctx.set_line_width(5)
        ctx.rectangle(2.5, 2.5, width - 5, height - 5)
        ctx.stroke()

        surface.flush()  # Important!
        return surface

    # --- Test the GUI ---
    print("Starting PDF Tester GUI...")
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 700
    start(WINDOW_WIDTH, WINDOW_HEIGHT)  # Pass desired window dimensions

    try:
        for i in range(1, 4):  # Test with 3 dummy pages
            print(f"\nRendering dummy page {i}...")
            # Image dimensions can be different from window dimensions
            page_surface = create_dummy_cairo_surface(600, 500, i)

            print(f"Showing page {i}. Please provide feedback in the GUI.")
            feedback = show_page(page_surface)

            if feedback is None:
                print("Window was closed by the user. Exiting test.")
                break
            elif feedback:
                print(f"Page {i}: User feedback = YES (rendered correctly)")
            else:
                print(f"Page {i}: User feedback = NO (rendered incorrectly)")

            # You might want a small delay or some other action here in a real test loop
            # time.sleep(0.5) # Optional small delay

    except tk.TclError as e:
        if "application has been destroyed" in str(e):
            print("GUI window was closed. Test interrupted.")
        else:
            raise  # Re-raise other TclErrors
    finally:
        print("\nTest finished. Closing GUI.")
        close_gui()
