import tkinter as tk
from tkinter import messagebox


def show_message():
    messagebox.showinfo("WSL2 Tkinter Test", "Hello from Tkinter in WSL2!")


# Create the main window
root = tk.Tk()
root.title("My WSL2 GUI App")
root.geometry("300x200")  # Set window size

# Create a label
label = tk.Label(root, text="Welcome to Tkinter on WSL2!")
label.pack(pady=20)  # Add some padding

# Create a button
button = tk.Button(root, text="Click Me!", command=show_message)
button.pack(pady=10)

# Start the GUI event loop
root.mainloop()
