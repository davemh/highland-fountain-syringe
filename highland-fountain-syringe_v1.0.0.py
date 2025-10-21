import os
import shutil
import zipfile
import base64
import json
import plistlib
import tkinter as tk
from tkinter import filedialog, messagebox

# ---------------- Extraction ---------------- #

def extract_highland(highland_path):
    """Extract text.md from a .highland and save as *_extraction.fountain."""
    try:
        base_dir = os.path.dirname(highland_path)
        filename = os.path.splitext(os.path.basename(highland_path))[0]
        temp_root = os.path.join(base_dir, "hfs_extract_temp")

        if os.path.exists(temp_root):
            shutil.rmtree(temp_root)
        os.makedirs(temp_root, exist_ok=True)

        # Copy .highland and treat as a zip
        zip_copy = os.path.join(temp_root, filename + ".zip")
        shutil.copy2(highland_path, zip_copy)

        with zipfile.ZipFile(zip_copy, "r") as z:
            z.extractall(temp_root)

        # Find .textbundle (top-level entry inside the extracted archive)
        textbundle_path = None
        for entry in os.listdir(temp_root):
            if entry.endswith(".textbundle"):
                textbundle_path = os.path.join(temp_root, entry)
                break
        if not textbundle_path:
            raise Exception("No .textbundle found inside .highland archive.")

        # Find the .md inside the textbundle (typically named text.md or similar)
        md_files = [f for f in os.listdir(textbundle_path) if f.endswith(".md")]
        if not md_files:
            raise Exception("No .md file found in .textbundle.")
        md_path = os.path.join(textbundle_path, md_files[0])

        # Copy out as .fountain
        fountain_out = os.path.join(base_dir, filename + "_extraction.fountain")
        shutil.copy2(md_path, fountain_out)

        messagebox.showinfo("Success", f"Extracted Fountain file:\n{fountain_out}")

    except Exception as e:
        messagebox.showerror("Extraction Failed", str(e))
    finally:
        if os.path.exists(temp_root):
            shutil.rmtree(temp_root, ignore_errors=True)


# ---------------- Injection ---------------- #

def _update_current_json_with_text(revisions_current_json_path, new_text):
    """
    revisions_current_json_path: path to revisions/current.json (a JSON with 'content' base64 bplist inside)
    new_text: unicode string to replace inside the plist's NS.string object
    """
    # Load current.json
    with open(revisions_current_json_path, "r", encoding="utf-8") as f:
        rev = json.load(f)

    if "content" not in rev:
        raise Exception("revisions/current.json missing 'content' field.")

    # Decode base64 -> binary plist bytes
    plist_bytes = base64.b64decode(rev["content"])

    # Load plist (binary) into Python object using plistlib
    plist_obj = plistlib.loads(plist_bytes)

    # The stored archived plist structure uses $objects array; find the object containing 'NS.string'
    # We will locate the first object (dict) that contains key 'NS.string' and replace it.
    objs = plist_obj.get("$objects")
    if not objs or not isinstance(objs, list):
        raise Exception("Unexpected plist structure in current.json (no $objects).")

    replaced = False
    for idx, o in enumerate(objs):
        if isinstance(o, dict) and "NS.string" in o:
            # Replace the NS.string value with the new text
            o["NS.string"] = new_text
            replaced = True
            break

    if not replaced:
        # Some variants might store the string under different keys (e.g., NS.storage string). Try searching strings.
        for idx, o in enumerate(objs):
            if isinstance(o, str):
                # unlikely, but skip
                continue
            if isinstance(o, dict):
                # find nested keys containing 'string' in name
                for k in list(o.keys()):
                    if isinstance(k, str) and "string" in k.lower():
                        o[k] = new_text
                        replaced = True
                        break
            if replaced:
                break

    if not replaced:
        raise Exception("Could not find 'NS.string' object inside plist to replace.")

    # Dump plist back to binary form
    new_plist_bytes = plistlib.dumps(plist_obj, fmt=plistlib.FMT_BINARY)

    # Base64-encode and write back to rev['content']
    rev["content"] = base64.b64encode(new_plist_bytes).decode("utf-8")

    # Save updated current.json (preserve other fields)
    with open(revisions_current_json_path, "w", encoding="utf-8") as f:
        json.dump(rev, f)


def inject_fountain(fountain_path, highland_path):
    """Inject a fountain file into a copy of the selected .highland project."""
    try:
        # Basic validation of inputs
        if not os.path.isfile(fountain_path):
            raise Exception("Selected fountain file does not exist.")
        if not os.path.isfile(highland_path):
            raise Exception("Selected highland file does not exist.")

        base_dir = os.path.dirname(highland_path)
        filename = os.path.splitext(os.path.basename(highland_path))[0]
        temp_root = os.path.join(base_dir, "hfs_inject_temp")

        # Prepare temp workspace
        if os.path.exists(temp_root):
            shutil.rmtree(temp_root)
        os.makedirs(temp_root, exist_ok=True)

        # Copy the .highland and extract it
        zip_copy = os.path.join(temp_root, filename + ".zip")
        shutil.copy2(highland_path, zip_copy)
        with zipfile.ZipFile(zip_copy, "r") as z:
            z.extractall(temp_root)

        # Remove the copied zip so it won't be re-included
        try:
            os.remove(zip_copy)
        except OSError:
            pass

        # Find .textbundle inside extracted root (top-level)
        textbundle_name = None
        for entry in os.listdir(temp_root):
            if entry.endswith(".textbundle"):
                textbundle_name = entry
                break
        if not textbundle_name:
            raise Exception("No .textbundle found inside .highland archive.")
        textbundle_path = os.path.join(temp_root, textbundle_name)

        # Find the primary .md file inside the textbundle
        md_files = [f for f in os.listdir(textbundle_path) if f.endswith(".md")]
        if not md_files:
            # Walk nested if not found directly inside bundle root
            md_files = []
            for root, dirs, files in os.walk(textbundle_path):
                for f in files:
                    if f.endswith(".md"):
                        md_files.append(os.path.join(root, f))
            if not md_files:
                raise Exception("No .md file found in .textbundle.")
            md_path = md_files[0]
        else:
            md_path = os.path.join(textbundle_path, md_files[0])

        # Read new fountain text
        with open(fountain_path, "r", encoding="utf-8") as f:
            fountain_data = f.read()

        # Overwrite the md file with new content
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(fountain_data)

        # Update revisions/current.json if it exists by replacing list object's NS.string
        revisions_dir = os.path.join(textbundle_path, "revisions")
        current_json_path = os.path.join(revisions_dir, "current.json")
        if os.path.exists(current_json_path):
            # Use helper to carefully preserve plist structure and only replace the embedded string
            _update_current_json_with_text(current_json_path, fountain_data)

        # Rebuild .highland archive:
        # IMPORTANT: The .textbundle must be a top-level entry inside the archive.
        injected_path = os.path.join(base_dir, filename + "_injected.highland")
        with zipfile.ZipFile(injected_path, "w", zipfile.ZIP_DEFLATED) as z:
            # Write the textbundle directory and its contents so that the .textbundle is top-level
            for root, dirs, files in os.walk(textbundle_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Build relative path so .textbundle/… is at top level
                    rel_path = os.path.relpath(file_path, temp_root)
                    z.write(file_path, rel_path)

            # Also include any other top-level files/folders from the original archive
            # (but skip the textbundle because it's already added)
            for entry in os.listdir(temp_root):
                entry_path = os.path.join(temp_root, entry)
                if entry == textbundle_name:
                    continue
                if os.path.isfile(entry_path):
                    # top-level file, add directly
                    z.write(entry_path, entry)
                elif os.path.isdir(entry_path):
                    # include directory contents
                    for root, dirs, files in os.walk(entry_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, temp_root)
                            z.write(file_path, rel_path)

        messagebox.showinfo("Success", f"Injected Highland file:\n{injected_path}")

    except Exception as e:
        messagebox.showerror("Injection Failed", str(e))
    finally:
        if os.path.exists(temp_root):
            shutil.rmtree(temp_root, ignore_errors=True)


# ---------------- GUI ---------------- #

class HighlandToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Highland Fountain Tool")
        self.root.geometry("540x420")  # slightly taller / wider

        self.mode = tk.StringVar(value="extract")

        tk.Label(root, text="Mode:").pack(pady=6)
        tk.Radiobutton(root, text="Extract Mode", variable=self.mode, value="extract",
                       command=self.update_mode).pack()
        tk.Radiobutton(root, text="Inject Mode", variable=self.mode, value="inject",
                       command=self.update_mode).pack()

        self.frame_extract = tk.Frame(root)
        self.frame_inject = tk.Frame(root)

        self.build_extract_ui()
        self.build_inject_ui()

        self.update_mode()

    def build_extract_ui(self):
        tk.Label(self.frame_extract, text="Select .highland file:").pack(pady=5)
        self.extract_path_var = tk.StringVar()
        tk.Entry(self.frame_extract, textvariable=self.extract_path_var, width=60).pack()
        tk.Button(self.frame_extract, text="Browse .highland",
                  command=lambda: self.extract_path_var.set(filedialog.askopenfilename(filetypes=[("Highland files", "*.highland")]))).pack(pady=6)
        tk.Button(self.frame_extract, text="Extract Fountain",
                  command=lambda: extract_highland(self.extract_path_var.get())).pack(pady=8)

    def build_inject_ui(self):
        tk.Label(self.frame_inject, text="Select .fountain file to inject:").pack(pady=5)
        self.inject_fountain_var = tk.StringVar()
        tk.Entry(self.frame_inject, textvariable=self.inject_fountain_var, width=60).pack()
        tk.Button(self.frame_inject, text="Browse .fountain",
                  command=lambda: self.inject_fountain_var.set(filedialog.askopenfilename(filetypes=[("Fountain files", "*.fountain")]))).pack(pady=6)

        tk.Label(self.frame_inject, text="Select .highland project to inject into:").pack(pady=5)
        self.inject_highland_var = tk.StringVar()
        tk.Entry(self.frame_inject, textvariable=self.inject_highland_var, width=60).pack()
        tk.Button(self.frame_inject, text="Browse .highland",
                  command=lambda: self.inject_highland_var.set(filedialog.askopenfilename(filetypes=[("Highland files", "*.highland")]))).pack(pady=6)

        tk.Button(self.frame_inject, text="Inject Fountain",
                  command=lambda: inject_fountain(self.inject_fountain_var.get(), self.inject_highland_var.get())).pack(pady=8)

    def update_mode(self):
        for frame in (self.frame_extract, self.frame_inject):
            frame.pack_forget()
        if self.mode.get() == "extract":
            self.frame_extract.pack(pady=10)
        else:
            self.frame_inject.pack(pady=10)


if __name__ == "__main__":
    root = tk.Tk()
    HighlandToolGUI(root)
    root.mainloop()
