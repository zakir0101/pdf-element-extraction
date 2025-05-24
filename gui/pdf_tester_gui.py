import tkinter as tk
from tkinter import font as tkFont
from PIL import Image, ImageTk
import cairo


# --- Global state for the GUI ---
_gui_root = None
_image_label = None
_user_response_var = None

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
        _user_response_var.set(STATE_DONE)
    if _gui_root:
        _gui_root.destroy()
        _gui_root = None


def close_gui():
    """Closes the GUI window if it's open."""
    global _gui_root
    if _gui_root and _gui_root.winfo_exists():
        _gui_root.destroy()
    _gui_root = None


# --- Exported API Functions ---

img_frame_width, img_frame_height = 0, 0
_canvas = None
_canvas_image_item = None
_photo_image_ref = None


def start(width, height):
    """
    Opens the GUI window with the specified dimensions.

    Args:
        width (int): The initial width of the GUI window.
        height (int): The initial height of the GUI window.
    """
    global _gui_root, _image_label, _user_response_var

    if _gui_root and _gui_root.winfo_exists():
        _gui_root.lift()
        return

    _gui_root = tk.Tk()
    pad = 50
    if width <= 0:
        width = _gui_root.winfo_screenwidth() - pad
    if height <= 0:
        height = _gui_root.winfo_screenheight() - pad

    _gui_root.title("PDF Page Rendering Test")
    _gui_root.geometry(f"{width}x{height}")
    _gui_root.protocol("WM_DELETE_WINDOW", _on_window_close)

    # --- Styling ---
    default_font = tkFont.nametofont("TkDefaultFont")
    default_font.configure(size=11)
    _gui_root.option_add("*Font", default_font)

    button_font = tkFont.Font(family="Helvetica", size=12, weight="bold")
    label_font = tkFont.Font(family="Helvetica", size=14)

    # --- Layout ---

    main_frame = tk.Frame(_gui_root, padx=15, pady=5)
    main_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
    control_frame = tk.Frame(_gui_root, padx=15, pady=15)
    control_frame.pack(fill=tk.Y, expand=False, side=tk.LEFT)

    global _canvas, _canvas_image_item, image_container_frame

    image_container_frame = tk.Frame(
        main_frame, relief=tk.SUNKEN, borderwidth=1
    )
    # This frame takes the place of your old 'image_frame' in the layout
    image_container_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

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

    v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
    _canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    _canvas_image_item = _canvas.create_image(0, 0, anchor=tk.NW, image=None)

    question_label = tk.Label(
        control_frame, text="Is this page rendered correctly?", font=label_font
    )
    question_label.pack(pady=(0, 15))
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
    _gui_root.bind_all("<Control-Z>", _on_yes_button)
    _gui_root.bind_all("<Control-n>", _on_no_button)
    _gui_root.bind_all("<Control-N>", _on_no_button)
    _gui_root.bind_all("<Control-q>", lambda x: _on_window_close())
    _gui_root.bind_all("<Control-Q>", lambda x: _on_window_close())

    # Initialize response variable for show_page
    _user_response_var = tk.StringVar(_gui_root)
    _user_response_var.set(STATE_WATING)

    _gui_root.update()


def show_page(
    cairo_image_surface: cairo.ImageSurface,
    adjust_height_to_fit,
    ratio: float | None = None,
):
    """
    Displays a single PDF page (from a Cairo ImageSurface) and waits for user feedback.

    Args:
        cairo_image_surface (cairo.ImageSurface): The Cairo surface containing the rendered page.
                                                 Assumed to be cairo.FORMAT_ARGB32 or cairo.FORMAT_RGB24.

    Returns:
        bool or None: True if user clicked "Yes", False if "No".
                      Returns None if the window was closed by the user before feedback.
    """
    global _gui_root, _user_response_var, adjust_height

    adjust_height = adjust_height_to_fit

    if not ratio:

        ratio = (
            cairo_image_surface.get_width() / cairo_image_surface.get_height()
        )

    if not _gui_root or not _gui_root.winfo_exists():
        print("Error: GUI not started or has been closed. Call start() first.")
        return None

    surface_format = cairo_image_surface.get_format()
    width = cairo_image_surface.get_width()
    height = cairo_image_surface.get_height()
    stride = cairo_image_surface.get_stride()

    cairo_image_surface.flush()

    image_data_buffer = cairo_image_surface.get_data()

    pil_image = None
    if surface_format == cairo.FORMAT_ARGB32:
        pil_image = Image.frombytes(
            "RGBA",
            (width, height),
            image_data_buffer.tobytes(),
            "raw",
            "BGRA",
            stride,
        )
    elif surface_format == cairo.FORMAT_RGB24:
        if stride == width * 3:
            pil_image = Image.frombytes(
                "RGB",
                (width, height),
                image_data_buffer.tobytes(),
                "raw",
                "BGR",
                stride,
            )
        elif stride >= width * 4:
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
            pil_image = Image.new("RGB", (width, height), "purple")

    else:
        print(f"Unsupported Cairo surface format: {surface_format}")

        pil_image = Image.new("RGB", (width, height), "red")
        draw = ImageDraw.Draw(pil_image)
        draw.text((10, 10), "Unsupported Format", fill="white")

    global img_copy, rel_scale

    rel_scale = ratio
    img_copy = pil_image.copy()

    global _photo_image_ref, _canvas, _canvas_image_item, image_container_frame

    if width > _canvas.winfo_width():
        width = _canvas.winfo_width()
        height = int(_canvas.winfo_width() / rel_scale)

    if adjust_height and height > _canvas.winfo_height():
        width = int(_canvas.winfo_height() * rel_scale)
        height = _canvas.winfo_height()

    pil_image = img_copy.resize((width, height))

    _photo_image_ref = ImageTk.PhotoImage(pil_image)

    _canvas.itemconfig(_canvas_image_item, image=_photo_image_ref)

    _canvas.config(scrollregion=(0, 0, width, height))
    _canvas.xview_moveto(0)
    _canvas.yview_moveto(0)

    _canvas.bind("<Configure>", _resize_image)
    _user_response_var.set(STATE_WATING)
    _gui_root.deiconify()  # Ensure window is visible if it was iconified
    _gui_root.lift()  # Bring to front
    _gui_root.focus_force()  # Try to grab focus

    _gui_root.wait_variable(_user_response_var)

    response_value = _user_response_var.get()

    return response_value


def _resize_image(event: tk.Event):
    global img_copy, rel_scale, _canvas, _photo_image_ref, adjust_height
    try:

        width = event.width
        heght = event.height

        if img_copy.width > event.width:
            width = width
            height = int(width / rel_scale)

        if adjust_height and img_copy.height > event.height:
            width = int(event.height * rel_scale)
            height = event.height

        print(f"new dim ({width},{height} )")
        image = img_copy.resize((width, height))
        _photo_image_ref = ImageTk.PhotoImage(image)
        _canvas.itemconfig(_canvas_image_item, image=_photo_image_ref)
        _canvas.config(scrollregion=(0, 0, width, height))

    except Exception as e:
        print(e)
        raise Exception(e)


if __name__ == "__main__":
    import time
    from PIL import (
        ImageDraw,
    )

    def create_dummy_cairo_surface(width, height, page_number):

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)

        if page_number % 2 == 0:
            ctx.set_source_rgba(0.9, 0.9, 0.7, 1)
        else:
            ctx.set_source_rgba(0.7, 0.9, 0.9, 1)
        ctx.paint()

        ctx.select_font_face(
            "Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
        )
        ctx.set_font_size(40)
        text = f"Page {page_number}"
        xbearing, ybearing, text_width, text_height, _, _ = ctx.text_extents(
            text
        )

        ctx.set_source_rgb(0.1, 0.1, 0.1)
        ctx.move_to(
            width / 2 - (xbearing + text_width / 2),
            height / 2 - (ybearing + text_height / 2),
        )
        ctx.show_text(text)

        ctx.set_source_rgb(0.3, 0.3, 0.3)
        ctx.set_line_width(5)
        ctx.rectangle(2.5, 2.5, width - 5, height - 5)
        ctx.stroke()

        surface.flush()
        return surface

    print("Starting PDF Tester GUI...")
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 700
    start(WINDOW_WIDTH, WINDOW_HEIGHT)

    try:
        for i in range(1, 4):
            print(f"\nRendering dummy page {i}...")

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

    except tk.TclError as e:
        if "application has been destroyed" in str(e):
            print("GUI window was closed. Test interrupted.")
        else:
            raise
    finally:
        print("\nTest finished. Closing GUI.")
        close_gui()
