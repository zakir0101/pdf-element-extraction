import asyncio
import os
import io
import tempfile
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

from markdown_it import MarkdownIt

"""
pip install markdown-it-pyh

# Install playwright and its browser binaries
pip install playwright
playwright install
"""


# --- Core Asynchronous Rendering Logic ---
async def _render_async(
    zip_dict: dict, output_png_path: str, temp_base_path: str
):
    """
    Asynchronously renders markdown and its related images from a dictionary
    to a PNG, cleaning up temporary files afterwards.
    """
    # Create a secure, unique temporary directory
    # It will be created inside the temp_base_path (e.g., "./")
    temp_dir = tempfile.mkdtemp(dir=temp_base_path)
    print(f"Created temporary directory: {temp_dir}")

    md_filename = None
    img_dir_name = None
    main_path = None
    images_p = []
    md_content = ""
    try:
        # --- Step 1: Reconstruct the file structure on disk ---
        for file_path, file_bytes in zip_dict.items():
            # Create the full path on the local filesystem

            # Keep track of the main markdown file
            if file_path.endswith(".md"):
                md_filename = file_path

                md_content = zip_dict[md_filename].decode("utf-8")
                # html_content = create_html_from_markdown(md_content)
                # file_bytes = html_content.encode("utf-8")
                main_path = os.path.join(
                    temp_dir, file_path.replace(".md", ".html")
                )
                # "index.html")
                continue

            else:
                disk_path = os.path.join(temp_dir, file_path)
                images_p.append(disk_path)
                img_dir_name = os.path.dirname(disk_path)
                os.makedirs(img_dir_name, exist_ok=True)

            with open(disk_path, "wb") as f:
                f.write(file_bytes)

        md_content = "<p>" + "<p></p>".join(md_content.split("\n")) + "</p>"

        md_content += "\n\n<br>\n<br># Images \n<br>\n<br>"
        for im_p in images_p:
            im_t = os.path.basename(im_p)
            url = Path(im_p).resolve().as_uri()
            md_content += (
                f"## {im_t}\n<br>"
                + f"<img src='{url}' alt='{url}'>\n<br>\n<br>"
            )

        html_content = f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body><div>{md_content}</div></body></html>"

        with open(main_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        if not md_filename:
            raise ValueError("No .md file found in the provided zip content.")
        #

        # --- Step 2: Render using Playwright ---
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})
            # await page.set_content(html_content)
            await page.goto(Path(main_path).resolve().as_uri())

            # Inject our GitHub-like CSS to make it look good
            css1 = """
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; margin: 0; }
                img { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; padding: 5px; }
                pre { background-color: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }
                code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 85%; }
                blockquote { border-left: 0.25em solid #dfe2e5; padding: 0 1em; color: #6a737d; }
                table { border-collapse: collapse; }
                th, td { border: 1px solid #ddd; padding: 8px; }
                h1, h2, h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; margin-top: 24px; margin-bottom: 16px; }
            """

            # old style
            css2 = """
                /* Universal box-sizing for predictable layouts */
                *, *::before, *::after {
                    box-sizing: border-box;
                }

                * {
                    font-size: 26px;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                    font-size: 26px;
                    line-height: 1.6;
                    color: #333;
                    max-width: 95%;
                    margin: 2em auto;
                    padding: 0;
                }
                h1, h2, h3 {
                    border-bottom: 1px solid #eaecef;
                    padding-bottom: .3em;
                    margin-top: 1.5em;
                    margin-bottom: 1em;
                    font-weight: 600;
                    line-height: 1.25;
                }
                h1 { font-size: 2em; }
                h2 { font-size: 1.5em; }
                h3 { font-size: 1.25em; }
                pre {
                    background-color: #f6f8fa;
                    padding: 16px;
                    border-radius: 6px;
                    overflow-x: auto;
                    font-size: 1.3em;
                }
                code {
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                }
                :not(pre) > code {
                    background-color: rgba(0, 0, 0, 0.05);
                    padding: .2em .4em;
                    border-radius: 4px;
                    font-size: 85%;
                }
                blockquote {
                    border-left: 0.25em solid #dfe2e5;
                    padding: 0 1em;
                    color: #6a737d;
                    margin-left: 0;
                    margin-right: 0;
                }
                img {
                    max-width: 100%;
                    height: auto;
                    border-radius: 6px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.07);
                }
                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
            """

            await page.add_style_tag(content=css2)
            # Take a screenshot of the entire rendered content

            # await page.screenshot(path=output_path, full_page=True, type="png")
            await page.screenshot(
                path=output_png_path, full_page=True, type="png"
            )
            await browser.close()

        print(f"✅ Successfully rendered content to {output_png_path}")

    finally:
        # --- Step 3: Clean up ---
        # This block executes whether the 'try' block succeeded or failed
        print(f"Cleaning up temporary directory: {temp_dir}")
        shutil.rmtree(temp_dir)


# --- Synchronous Wrapper for Easy GUI Integration ---
def render_markdown_to_png(
    zip_dict: dict, output_png_path: str, temp_base_path: str = "./"
):
    """
    Synchronous wrapper to render markdown from a zip dictionary to a PNG file.

    Args:
        zip_dict: Dictionary mapping file paths to their byte content.
        output_png_path: The file path to save the final PNG.
        temp_base_path: The directory where temporary files will be created.
    """
    if not zip_dict:
        print("Error: The provided zip dictionary is empty.")
        return

    # On Windows, you might need this policy if you run into event loop errors

    if os.name == "nt":  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(_render_async(zip_dict, output_png_path, temp_base_path))


def create_html_from_markdown(
    markdown_text: str, image_path: str = None
) -> str:
    """
    Converts a markdown string to a full HTML document with styling.
    Handles embedding a local image if provided.
    """
    md = MarkdownIt()

    css = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; }
        img { max-width: 100%; height: auto; }
        pre { background-color: #f6f8fa; padding: 16px; border-radius: 6px; }
        code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; }
        blockquote { border-left: 0.25em solid #dfe2e5; padding: 0 1em; color: #6a737d; }
        h1, h2, h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; }
    </style>
    """

    body_html = md.render(markdown_text)

    # {css}
    full_html = f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{body_html}</body></html>"
    return full_html


# async def render_markdown_to_png_async(
#     markdown_text: str, output_path: str, image_to_embed: str = None
# ):
#     html_content = create_html_from_markdown(markdown_text, image_to_embed)
#     async with async_playwright() as p:
#         browser = await p.chromium.launch()
#         page = await browser.new_page()
#         await page.set_content(html_content)
#         await page.screenshot(path=output_path, full_page=True, type="png")
#         await browser.close()
#     print(f"✅ Successfully rendered markdown to {output_path}")


# def render_markdown_to_png(
#     markdown_text: str, output_path: str, image_to_embed: str = None
# ):
#     asyncio.run(
#         render_markdown_to_png_async(
#             markdown_text, output_path, image_to_embed
#         )
#     )


# --- Example of how you would call it ---
if __name__ == "__main__":
    # 1. Simulate the zip_dict you get from the server
    # Create a dummy image (a small red square)
    from PIL import Image

    img_bytes = io.BytesIO()
    Image.new("RGB", (100, 50), color="red").save(img_bytes, format="PNG")

    # Create sample markdown that references the image with a relative path
    sample_markdown = """
# Analysis Result

Here is the analysis of the provided document.

## Key Findings
- **Item 1:** The primary subject is a cat.
- **Item 2:** The background is blurry.

```python
# This is a code block
def hello():
    print("Hello from Markdown!")
```

> This is a blockquote, indicating an important note.


![Extracted red box](./nr1_images/some_image.png)
"""
    # Create the dictionary that mimics your zip structure
    mock_zip_dict = {
        "nr1_md_content.md": sample_markdown.encode("utf-8"),
        "nr1_images/some_image.png": img_bytes.getvalue(),
    }

    # 2. Define where you want the final output
    output_path = "final_report.png"

    # 3. Call the function
    print("Starting markdown rendering process...")
    render_markdown_to_png(mock_zip_dict, output_path, "./")
    print(f"\nProcess complete. Check for the output file at: {output_path}")
