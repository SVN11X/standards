#!/usr/bin/env python3
"""Measure the UX of a desktop app: what a program can check in its windows, and what only people can show.

Usage:
  python scripts/desktop_ux.py tk MODULE:FACTORY [--src DIR] [--sizes 1024x700,800x600] [--scale S] [--shots DIR] [--json] [--strict]
  python scripts/desktop_ux.py uia --title TEXT [--json] [--strict]
  python scripts/desktop_ux.py shot --title TEXT --out FILE.png
  python scripts/desktop_ux.py protocol --app NAME --task "TEXT" [--task "TEXT" ...] [--out DIR]
  python scripts/desktop_ux.py evidence [DIR] [--json]

tk builds a tkinter window in this process: FACTORY(root) must build the interface on the Tk root it gets. It opens
every tab of every notebook at every size, checks contrast, text size, target size and spacing, text cut by the
layout, and controls a mouse reaches and the keyboard does not, and can save one screenshot per tab and size.
uia reads the UI Automation tree of a running window of any technology (Win32, WinForms, WPF, Go, Electron) with
pywinauto, and checks names, keyboard focus, target size and controls cut off by the window. shot saves a window.
protocol writes a usability test card for five people, and evidence reads the filled cards: task success, time
and the System Usability Scale. The rules are signals. Only people doing the tasks show that the app helps them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

SCHEMA = "standards/desktop-ux/v1"
SOURCES = {
    "contrast": "WCAG 2.2, 1.4.3 Contrast (Minimum): 4.5:1, or 3:1 for text of 18 pt, or 14 pt bold. "
                "https://www.w3.org/TR/WCAG22/#contrast-minimum",
    "target": "WCAG 2.2, 2.5.8 Target Size (Minimum): 24 by 24 CSS pixels, or a 24 pixel circle that touches no other target. "
              "https://www.w3.org/TR/WCAG22/#target-size-minimum. Windows asks 23 by 23 relative pixels: "
              "https://learn.microsoft.com/windows/win32/uxguide/inter-touch",
    "spacing": "Windows UX guidelines, Layout: target regions of interactive controls touch or keep 5 relative pixels apart. "
               "https://learn.microsoft.com/windows/win32/uxguide/vis-layout",
    "font": "Windows UX guidelines, Fonts: use Segoe UI at 9 points or larger. https://learn.microsoft.com/windows/win32/uxguide/vis-fonts",
    "clipped": "Windows UX guidelines, Layout: size controls to their longest text, plus 30 percent for translation. "
               "https://learn.microsoft.com/windows/win32/uxguide/vis-layout",
    "keyboard": "WCAG 2.2, 2.1.1 Keyboard: every function works from the keyboard. https://www.w3.org/TR/WCAG22/#keyboard",
    "name": "WCAG 2.2, 4.1.2 Name, Role, Value: every control has a name assistive technology reads. "
            "https://www.w3.org/TR/WCAG22/#name-role-value",
    "labels": "WCAG 2.2, 2.4.6 Headings and Labels: labels describe their purpose. https://www.w3.org/TR/WCAG22/#headings-and-labels",
    "sus": "Brooke 1996, the System Usability Scale, retold in Brooke 2013: https://uxpajournal.org/sus-a-retrospective/. "
           "68 is the average score of hundreds of studies (Sauro 2011)",
    "people": "Nielsen and Landauer 1993: five people find most usability problems of a design. "
              "https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/",
    "heuristics": "Nielsen 1994, ten usability heuristics. https://www.nngroup.com/articles/ten-usability-heuristics/",
    "screen-reader": "The audit cannot hear what a screen reader says. Do the main task once with Narrator (Ctrl+Win+Enter)",
}
# The ten statements of the System Usability Scale (Brooke 1996), answered from 1 (strongly disagree) to 5 (strongly agree).
SUS_EN = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]
SUS_ES = [
    "Creo que me gustaría usar este sistema con frecuencia.",
    "El sistema me pareció innecesariamente complejo.",
    "Pensé que el sistema era fácil de usar.",
    "Creo que necesitaría el apoyo de una persona técnica para poder usar este sistema.",
    "Las distintas funciones del sistema me parecieron bien integradas.",
    "Pensé que el sistema tenía demasiadas inconsistencias.",
    "Imagino que la mayoría de las personas aprendería a usar este sistema muy rápido.",
    "El sistema me pareció muy engorroso de usar.",
    "Me sentí muy seguro al usar el sistema.",
    "Necesité aprender muchas cosas antes de poder empezar a usar este sistema.",
]
TARGET_PX = 24
SPACING_PX = 5
MIN_POINTS = 9


# Rules on plain numbers, shared by tk and uia


def luminance(rgb: tuple[float, float, float]) -> float:
    """Relative luminance of a color with channels from 0 to 1 (WCAG 2.2)."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 2)


def large_text(points: float, bold: bool) -> bool:
    return points >= 18 or (bold and points >= 14)


def gap(a: tuple, b: tuple) -> float:
    """Distance between two rectangles (left, top, right, bottom). 0 when they touch or overlap."""
    dx = max(0, a[0] - b[2], b[0] - a[2])
    dy = max(0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def circle_hits(center: tuple[float, float], radius: float, rect: tuple) -> bool:
    x = min(max(center[0], rect[0]), rect[2])
    y = min(max(center[1], rect[1]), rect[3])
    return math.hypot(center[0] - x, center[1] - y) < radius


def target_findings(targets: list[dict], scale: float) -> list[dict]:
    """WCAG 2.5.8 with its spacing exception, and the 5 pixel spacing of the Windows layout guidelines.

    Each target is {"where": text, "rect": (left, top, right, bottom)} in device pixels; scale is device pixels per
    CSS or relative pixel (1 at 96 dpi)."""
    side, out = TARGET_PX * scale, []
    small = [t for t in targets if t["rect"][2] - t["rect"][0] < side or t["rect"][3] - t["rect"][1] < side]
    centers = {id(t): ((t["rect"][0] + t["rect"][2]) / 2, (t["rect"][1] + t["rect"][3]) / 2) for t in targets}
    for t in small:
        others = [o for o in targets if o is not t]
        crowded = (any(circle_hits(centers[id(t)], side / 2, o["rect"]) for o in others)
                   or any(math.dist(centers[id(t)], centers[id(o)]) < side for o in small if o is not t))
        if crowded:
            w, h = t["rect"][2] - t["rect"][0], t["rect"][3] - t["rect"][1]
            out.append(finding("target", "error", t["where"],
                               f"{round(w / scale)} by {round(h / scale)} px, smaller than {TARGET_PX} by {TARGET_PX} and too close to "
                               "another target"))
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            space = gap(a["rect"], b["rect"])
            if 0 < space < SPACING_PX * scale:
                out.append(finding("spacing", "warning", f"{a['where']} and {b['where']}",
                                   f"{round(space / scale, 1)} px apart: a click between them does nothing"))
    return out


def finding(rule: str, severity: str, where: str, detail: str) -> dict:
    return {"rule": rule, "severity": severity, "where": where, "detail": detail, "source": SOURCES[rule]}


# tkinter, measured in its own process

TK_TARGETS = {"Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton", "Menubutton", "TMenubutton",
              "TCombobox", "Spinbox", "TSpinbox", "Scale", "TScale", "Entry", "TEntry"}
TK_TEXT = {"Label", "TLabel", "Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton", "Message",
           "Menubutton", "TMenubutton", "Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox", "Labelframe", "TLabelframe"}
TK_ONE_LINE = {"Label", "TLabel", "Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton"}
TK_PASSIVE = {"Label", "TLabel", "Frame", "TFrame", "Canvas", "Message", "Labelframe", "TLabelframe"}
CLICKS = ("<Button-1>", "<ButtonRelease-1>", "<Double-Button-1>")
KEYS = ("<Key-Return>", "<Return>", "<Key-space>", "<space>", "<Key>", "<KeyPress>", "<Key-KP_Enter>")


def tk_widgets(root) -> list:
    out, stack = [], [root]
    while stack:
        widget = stack.pop()
        out.append(widget)
        stack.extend(reversed(widget.winfo_children()))
    return out


def tk_option(widget, name: str) -> str:
    """An option of a classic widget, or the value its ttk style gives."""
    try:
        return str(widget.cget(name))
    except Exception:  # noqa: BLE001 (a ttk widget keeps colors in its style)
        pass
    from tkinter import ttk
    try:
        style = str(widget.cget("style")) or widget.winfo_class()
    except Exception:  # noqa: BLE001
        style = widget.winfo_class()
    lookup = ttk.Style(widget)
    return str(lookup.lookup(style, name, ["!disabled"]) or lookup.lookup(".", name) or "")


def tk_background(widget) -> str:
    while widget is not None:
        value = tk_option(widget, "background")
        if value:
            return value
        widget = widget.master
    return "white"


def tk_rgb(widget, color: str) -> tuple[float, float, float]:
    return tuple(c / 65535 for c in widget.winfo_rgb(color))


def tk_font(widget) -> tuple[float, bool]:
    from tkinter import font as tkfont
    spec = tk_option(widget, "font") or "TkDefaultFont"
    try:
        actual = tkfont.Font(root=widget, font=spec).actual()
    except Exception:  # noqa: BLE001 (a named font the style left unset)
        actual = tkfont.nametofont("TkDefaultFont").actual()
    size = actual.get("size", 9)
    points = size if size > 0 else -size * 72 / widget.winfo_fpixels("1i")
    return float(points), actual.get("weight") == "bold"


def tk_natural(widget) -> tuple[int, int]:
    """The size a one line widget asks for with all its text. A width fixed in characters cuts the text and also
    sets the size it asks for, so that width is lifted for one reading and put back before the window redraws."""
    try:
        width = str(widget.cget("width"))
    except Exception:  # noqa: BLE001 (no width option)
        width = ""
    if width in ("", "0") or width.startswith("-"):
        return widget.winfo_reqwidth(), widget.winfo_reqheight()
    try:
        widget.configure(width="" if widget.winfo_class().startswith("T") else 0)
        return widget.winfo_reqwidth(), widget.winfo_reqheight()
    finally:
        widget.configure(width=width)


def tk_disabled(widget) -> bool:
    try:
        return "disabled" in str(widget.cget("state"))
    except Exception:  # noqa: BLE001
        try:
            return widget.instate(["disabled"])
        except Exception:  # noqa: BLE001
            return False


def tk_label(widget) -> str:
    text = ""
    if widget.winfo_class() in TK_ONE_LINE | {"Labelframe", "TLabelframe", "Menubutton", "TMenubutton"}:
        text = str(widget.cget("text")).strip()
    elif hasattr(widget, "get"):
        try:
            text = str(widget.get()).strip()
        except Exception:  # noqa: BLE001 (a widget whose get needs arguments)
            text = ""
    return f"{widget.winfo_class()} {widget}" + (f" \"{text[:40]}\"" if text else "")


def tk_audit(root, where: str = "") -> list[dict]:
    """The findings of every mapped widget of one window as it is drawn now."""
    root.update_idletasks()
    scale = root.winfo_fpixels("1i") / 96
    out, targets = [], []
    need_w, need_h, has_w, has_h = root.winfo_reqwidth(), root.winfo_reqheight(), root.winfo_width(), root.winfo_height()
    if need_w > has_w + 1 or need_h > has_h + 1:
        # A geometry manager hides what does not fit, so the controls left out are not even mapped.
        minimum = root.minsize()
        out.append(finding("clipped", "error", "the window",
                           f"its content needs {need_w} by {need_h} px and it has {has_w} by {has_h}: what does not fit is hidden. "
                           f"Its minimum size is {minimum[0]} by {minimum[1]}: raise it or let the content scroll"))
    for widget in tk_widgets(root):
        if widget is root or not widget.winfo_ismapped():
            continue
        cls, label = widget.winfo_class(), tk_label(widget)
        x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
        disabled = tk_disabled(widget)
        if cls in TK_TEXT and not disabled:
            points, bold = tk_font(widget)
            fg, bg = tk_option(widget, "foreground"), tk_background(widget)
            if fg and bg:
                ratio = contrast(tk_rgb(widget, fg), tk_rgb(widget, bg))
                need = 3.0 if large_text(points, bold) else 4.5
                if ratio < need:
                    out.append(finding("contrast", "error", label, f"{ratio}:1 for {fg} on {bg}, needs {need}:1"))
            if points < MIN_POINTS - 0.25:
                out.append(finding("font", "warning", label, f"{round(points, 1)} pt"))
        if cls in TK_ONE_LINE:
            need_w, need_h = tk_natural(widget)
            if need_w > w + 1 or need_h > h + 1:
                out.append(finding("clipped", "warning", label, f"its text needs {need_w} by {need_h} px and has {w} by {h}"))
        if cls in TK_TARGETS and not disabled:
            targets.append({"where": label, "rect": (x, y, x + w, y + h)})
            if str(widget.cget("takefocus")) in ("0", "False", "false"):
                out.append(finding("keyboard", "error", label, "takefocus is off, so Tab never reaches it"))
        elif cls in TK_PASSIVE:
            bound = set(widget.bind())
            if bound & set(CLICKS) and not bound & set(KEYS):
                targets.append({"where": label, "rect": (x, y, x + w, y + h)})
                out.append(finding("keyboard", "error", label, "a click does something here and no key does"))
    out.extend(target_findings(targets, scale))
    for item in out:
        item["at"] = where
    return out


def tk_shot(root, path: Path) -> str | None:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "no screenshot: Pillow is not installed. python -m pip install pillow"
    root.lift()
    root.update()
    time.sleep(0.3)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    box = (x, y, x + root.winfo_width(), y + root.winfo_height())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ImageGrab.grab(bbox=box, all_screens=True).save(path)
    except Exception as error:  # noqa: BLE001 (no display to grab from)
        return f"no screenshot: {error}"
    return None


def notebooks(root) -> list:
    return [w for w in tk_widgets(root) if w.winfo_class() == "TNotebook"]


def tk_states(root):
    """Every tab of every notebook, one at a time, and the window as it opens when there is none."""
    books = notebooks(root)
    if not books:
        yield "window"
        return
    for book in books:
        for tab in book.tabs():
            if not book.winfo_ismapped():
                continue
            book.select(tab)
            root.update()
            yield f"tab {book.tab(tab, 'text')}"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "window"


def run_tk(target: str, src: list[str], sizes: list[tuple[int, int]], scale: float | None, shots: Path | None) -> dict:
    if os.name == "nt":
        try:  # the window and the screenshot then use the same pixels at any Windows scaling
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001 (older Windows)
            pass
    for folder in [*src, "src", "."]:
        path = str(Path(folder).resolve())
        if path not in sys.path:
            sys.path.insert(0, path)
    module, _, name = target.partition(":")
    factory = getattr(importlib.import_module(module), name or "main")
    import tkinter as tk
    root = tk.Tk()
    if scale:
        root.tk.call("tk", "scaling", 96 * scale / 72)
    app = factory(root)
    findings, pictures, notes = [], [], []
    seen = set()
    for width, height in sizes:
        root.geometry(f"{width}x{height}")
        root.update()
        for state in tk_states(root):
            where = f"{width}x{height}, {state}"
            for item in tk_audit(root, where):
                key = (item["rule"], item["where"], item["detail"])
                if key not in seen:
                    seen.add(key)
                    findings.append(item)
            if shots:
                path = shots / f"{width}x{height}-{slug(state)}.png"
                problem = tk_shot(root, path)
                if problem:
                    notes.append(problem)
                else:
                    pictures.append(str(path))
    for stop in ("stop", "close", "quit"):
        part = getattr(getattr(app, "tray", None), stop, None)
        if callable(part):
            try:
                part()
            except Exception:  # noqa: BLE001
                pass
            break
    from tkinter import ttk
    import platform
    notes.insert(0, f"measured with the ttk theme {ttk.Style(root).theme_use()} at {round(root.winfo_fpixels('1i'))} dpi on "
                    f"{platform.system()}. Sizes change with the theme and the fonts: measure on the system the app targets")
    root.destroy()
    notes.append(SOURCES["screen-reader"])
    return report("tk", target, findings, pictures, notes)


# UI Automation, from outside the process

UIA_TARGETS = {"Button", "CheckBox", "RadioButton", "ComboBox", "Edit", "Hyperlink", "ListItem", "MenuItem", "Slider", "Spinner",
               "TabItem", "TreeItem", "SplitButton", "DataItem"}
UIA_FOCUS_BY_ARROWS = {"ListItem", "TreeItem", "TabItem", "MenuItem", "DataItem", "RadioButton"}


def uia_findings(items: list[dict], window: tuple, scale: float) -> list[dict]:
    """Rules on the elements of a UI Automation tree: {name, type, rect, focusable, enabled, offscreen}."""
    out, targets, names = [], [], {}
    for item in items:
        if item.get("type") not in UIA_TARGETS or item.get("offscreen") or not item.get("enabled", True):
            continue
        where = f"{item['type']} \"{item.get('name') or ''}\"" + (f" ({item['id']})" if item.get("id") else "")
        rect = tuple(item["rect"])
        if not str(item.get("name") or "").strip():
            out.append(finding("name", "error", where, "no name: a screen reader says only its type"))
        if not item.get("focusable") and item["type"] not in UIA_FOCUS_BY_ARROWS:
            out.append(finding("keyboard", "error", where, "not keyboard focusable"))
        if rect[0] < window[0] or rect[1] < window[1] or rect[2] > window[2] or rect[3] > window[3]:
            out.append(finding("clipped", "warning", where, "partly outside its window"))
        targets.append({"where": where, "rect": rect})
        if item["type"] == "Button" and item.get("name"):
            names.setdefault(item["name"].strip().lower(), []).append(where)
    out.extend(target_findings(targets, scale))
    out.extend(finding("labels", "warning", " and ".join(found[:3]), "buttons with the same name do different things or one is extra")
               for found in names.values() if len(found) > 1)
    return out


def run_uia(title: str) -> dict:
    if os.name != "nt":
        raise SystemExit("uia reads Windows UI Automation and runs on Windows only")
    try:
        from pywinauto import Desktop
    except ImportError as error:
        raise SystemExit("pywinauto is not installed: python -m pip install pywinauto") from error
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    window = Desktop(backend="uia").window(title_re=f".*{re.escape(title)}.*", visible_only=True)
    window.wait("visible", timeout=20)
    wrapper = window.wrapper_object()
    box = wrapper.rectangle()
    dpi = ctypes.windll.user32.GetDpiForWindow(wrapper.handle) or 96
    items = []
    for element in wrapper.descendants():
        info, rect = element.element_info, element.element_info.rectangle
        raw = getattr(info, "element", None)
        items.append({"name": info.name, "type": info.control_type, "id": info.automation_id,
                      "rect": (rect.left, rect.top, rect.right, rect.bottom), "enabled": info.enabled,
                      "focusable": bool(getattr(raw, "CurrentIsKeyboardFocusable", True)),
                      "offscreen": bool(getattr(raw, "CurrentIsOffscreen", False))})
    findings = uia_findings(items, (box.left, box.top, box.right, box.bottom), dpi / 96)
    notes = [f"{len(items)} elements read from \"{wrapper.window_text()}\"",
             "Axe.Windows checks many more UI Automation rules: AxeWindowsCLI --processId <pid>", SOURCES["screen-reader"]]
    return report("uia", title, findings, [], notes)


def run_shot(title: str, out: Path) -> dict:
    if os.name != "nt":
        raise SystemExit("shot finds a window by its title on Windows. For tkinter use: tk MODULE:FACTORY --shots DIR")
    import ctypes
    from ctypes import wintypes
    try:
        from PIL import ImageGrab
    except ImportError as error:
        raise SystemExit("Pillow is not installed: python -m pip install pillow") from error
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    user32, found = ctypes.windll.user32, []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if title.lower() in buffer.value.lower():
                found.append((hwnd, buffer.value))
        return True
    user32.EnumWindows(visit, 0)
    if not found:
        raise SystemExit(f"no visible window has \"{title}\" in its title")
    hwnd, name = found[0]
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    rect = wintypes.RECT()
    # The frame Windows draws, without the invisible resize border GetWindowRect adds.
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    out.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(out)
    return {"schema": SCHEMA, "kind": "shot", "window": name, "file": str(out), "size": [rect.right - rect.left, rect.bottom - rect.top]}


def report(kind: str, target: str, findings: list[dict], pictures: list[str], notes: list[str]) -> dict:
    order = {"error": 0, "warning": 1}
    findings.sort(key=lambda f: (order[f["severity"]], f["rule"], f["where"]))
    counts = {s: sum(f["severity"] == s for f in findings) for s in order}
    return {"schema": SCHEMA, "kind": kind, "target": target, "counts": counts, "findings": findings, "screenshots": pictures,
            "notes": notes, "heuristics": SOURCES["heuristics"]}


def summary(result: dict) -> str:
    lines = [f"{result['kind']} {result['target']}: {result['counts']['error']} errors, {result['counts']['warning']} warnings"]
    for item in result["findings"]:
        at = f" [{item['at']}]" if item.get("at") else ""
        lines.append(f"{item['severity'].upper():8}{item['rule']:9}{item['where']}{at}: {item['detail']}")
    rules = sorted({f["rule"] for f in result["findings"]})
    lines += [f"source {rule}: {SOURCES[rule]}" for rule in rules]
    lines += [f"screenshot: {path}" for path in result["screenshots"]]
    lines += [f"note: {note}" for note in result["notes"]]
    lines.append(f"Then judge the screenshots against {SOURCES['heuristics']}")
    return "\n".join(lines)


# Usability tests with people


def protocol(app: str, tasks: list[str], out: Path, today: str | None = None) -> Path:
    """A usability test card for five people. It holds no result until people do the tasks."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slug(app)}-usability.yml"
    if path.exists():
        raise FileExistsError(f"{path} exists. Add a new round to it instead of starting over.")
    today = today or dt.date.today().isoformat()
    statements = "\n".join(f"#  {i}. {es} ({en})" for i, (es, en) in enumerate(zip(SUS_ES, SUS_EN), 1))
    task_list = "\n".join(f"  - {json.dumps(t, ensure_ascii=False)}" for t in tasks)
    task_rows = "\n".join("          - {done: null, seconds: null, errors: null, hesitated_at: \"\"}" for _ in tasks)
    path.write_text(f"""# Usability test of {app}. Created {today} by scripts/desktop_ux.py protocol.
# Five people of the audience, one at a time, who did not build the app (Nielsen and Landauer 1993).
# 1. Give each task below in words, say nothing more, and ask the person to think aloud. Never help or point.
# 2. For each task write done (true, partial or false), the seconds it took, the errors, and where the person hesitated.
# 3. After the tasks, read the ten statements and write the answers from 1 (strongly disagree) to 5 (strongly agree).
#    The Spanish wording is this standard's translation, not a validated version.
{statements}
# Write what happened, not what the person said they would do. Change the app, then test again in a new round.
kind: usability
app: {json.dumps(app, ensure_ascii=False)}
tasks:
{task_list}
rounds:
  - date: ""
    app_version: ""
    participants:
      # One entry per person. who: role or level only, never a name.
      - who: ""
        tasks:
{task_rows}
        sus: []
    decision: ""           # what changes in the app because of this round
""", encoding="utf-8")
    return path


def sus_score(answers: list) -> float | None:
    if len(answers) != 10 or not all(isinstance(a, int) and 1 <= a <= 5 for a in answers):
        return None
    return sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers)) * 2.5


def evidence(folder: Path) -> dict:
    """What the usability cards in a folder show. A round counts once five people did it."""
    import yaml
    tests = []
    for path in sorted(folder.glob("*.yml")) if folder.is_dir() else []:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            tests.append({"file": str(path), "problem": f"not valid YAML: {str(error).splitlines()[0]}"})
            continue
        if data.get("kind") != "usability":
            continue
        tasks = [str(t) for t in data.get("tasks") or []]
        rounds = [r for r in data.get("rounds") or [] if isinstance(r, dict)]
        last = rounds[-1] if rounds else {}
        people = [p for p in last.get("participants") or [] if isinstance(p, dict)
                  and any(isinstance(t, dict) and t.get("done") is not None for t in p.get("tasks") or [])]
        rows = []
        for index, task in enumerate(tasks):
            done = [p["tasks"][index] for p in people if len(p.get("tasks") or []) > index and isinstance(p["tasks"][index], dict)
                    and p["tasks"][index].get("done") is not None]
            value = {True: 1.0, "partial": 0.5, False: 0.0}
            rate = [value.get(t["done"], 0.0) for t in done]
            seconds = [t["seconds"] for t in done if isinstance(t.get("seconds"), (int, float))]
            rows.append({"task": task, "people": len(done), "success_rate": round(sum(rate) / len(rate), 2) if rate else None,
                         "median_seconds": statistics.median(seconds) if seconds else None,
                         "errors": sum(t["errors"] for t in done if isinstance(t.get("errors"), int)),
                         "hesitated_at": [t["hesitated_at"] for t in done if t.get("hesitated_at")]})
        scores = [s for s in (sus_score(p.get("sus") or []) for p in people) if s is not None]
        state = "not run" if not people else "too few people" if len(people) < 5 else "tested"
        tests.append({"file": str(path), "app": data.get("app"), "rounds": len(rounds), "people": len(people), "state": state,
                      "tasks": rows, "sus_mean": round(statistics.mean(scores), 1) if scores else None, "sus_answers": len(scores),
                      "sus_vs_average": None if not scores else "above" if statistics.mean(scores) > 68 else "at or below",
                      "decision": last.get("decision") or None})
    return {"schema": SCHEMA, "kind": "evidence", "tests": tests, "sources": [SOURCES["people"], SOURCES["sus"]]}


def evidence_summary(result: dict) -> str:
    if not result["tests"]:
        return "No usability card yet. Write one with: python scripts/desktop_ux.py protocol --app NAME --task \"...\""
    lines = []
    for test in result["tests"]:
        if test.get("problem"):
            lines.append(f"{test['file']}: {test['problem']}")
            continue
        sus = f", SUS {test['sus_mean']} ({test['sus_vs_average']} the average of 68)" if test["sus_mean"] is not None else ""
        lines.append(f"{test['app']}: {test['state']}, {test['people']} people in round {test['rounds']}{sus}")
        for row in test["tasks"]:
            if row["people"]:
                lines.append(f"  {row['task']}: {round(row['success_rate'] * 100)}% done, median {row['median_seconds']} s, "
                             f"{row['errors']} errors" + (f", hesitated at: {'; '.join(row['hesitated_at'][:3])}" if row["hesitated_at"] else ""))
    lines += [f"source: {source}" for source in result["sources"]]
    return "\n".join(lines)


def sizes_of(text: str) -> list[tuple[int, int]]:
    out = []
    for part in text.split(","):
        found = re.fullmatch(r"\s*(\d+)x(\d+)\s*", part)
        if not found:
            raise argparse.ArgumentTypeError(f"not a size: {part!r}. Write it as 1024x700")
        out.append((int(found.group(1)), int(found.group(2))))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("tk", help="audit a tkinter interface built in this process")
    p.add_argument("target", help="MODULE:FACTORY, a callable that builds the interface on the Tk root it gets")
    p.add_argument("--src", action="append", default=[], help="a folder to import from (src and . are always tried)")
    p.add_argument("--sizes", type=sizes_of, default=sizes_of("1024x700,800x600"))
    p.add_argument("--scale", type=float, help="text scale to try, like Windows display scaling: 1.25 or 1.5")
    p.add_argument("--shots", type=Path, help="folder for one screenshot per size and tab")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit 1 when there is an error")
    p = sub.add_parser("uia", help="audit a running window through Windows UI Automation")
    p.add_argument("--title", required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p = sub.add_parser("shot", help="save a screenshot of a running window on Windows")
    p.add_argument("--title", required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("protocol", help="write a usability test card for five people")
    p.add_argument("--app", required=True)
    p.add_argument("--task", action="append", required=True)
    p.add_argument("--out", type=Path, default=Path("docs") / "usability")
    p = sub.add_parser("evidence", help="what the filled usability cards show")
    p.add_argument("folder", nargs="?", type=Path, default=Path("docs") / "usability")
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "protocol":
        try:
            print(f"wrote {protocol(args.app, args.task, args.out)}")
        except FileExistsError as error:
            print(error)
            return 1
        return 0
    if args.command == "evidence":
        result = evidence(args.folder)
        print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else evidence_summary(result))
        return 0
    if args.command == "shot":
        print(json.dumps(run_shot(args.title, args.out), indent=2, ensure_ascii=False))
        return 0
    result = run_tk(args.target, args.src, args.sizes, args.scale, args.shots) if args.command == "tk" else run_uia(args.title)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else summary(result))
    sys.stdout.flush()
    code = 1 if args.strict and result["counts"]["error"] else 0
    if args.command == "tk":
        # An app may leave threads behind (a tray icon, a timer). The report is out, so nothing is waited for.
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
