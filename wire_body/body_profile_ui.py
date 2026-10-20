"""Body profile window for the wire body.

Type in a set of body measurements, save them under a person's name and a date,
and come back later to add another dated entry. Each person gets one file in
PROFILE_DIR holding every entry saved for them, so progress can be followed over time.

Choosing a saved profile also reshapes the wire body in the scene: the slider at the
bottom runs from 0 (the neutral body) through each saved entry in date order, and the
body's height and the thickness of its trunk, arms and legs follow the numbers.

Open the window in Maya with:
    import body_profile_ui; body_profile_ui.show()
"""
import datetime
import importlib
import json
import math
import os
import re

import maya.cmds as cmds

WINDOW = "wireBodyProfileWindow"
PROFILE_DIR = os.path.expanduser("~/Documents/wire_body/profiles")
NEW_PROFILE = "New profile..."

# (key used in the saved file, label shown in the window), in the order they appear
MEASUREMENTS = [
    ("weight", "Weight (lbs)"),
    ("water_weight", "Water Weight (lbs)"),
    ("dry_lean_mass", "Dry Lean Mass (lbs)"),
    ("body_fat_mass", "Body Fat Mass (lbs)"),
    ("skeletal_muscle_mass", "Skeletal Muscle Mass (lbs)"),
    ("percent_body_fat", "Percent Body Fat (%)"),
    ("right_arm", "Right Arm (lbs)"),
    ("left_arm", "Left Arm (lbs)"),
    ("trunk", "Trunk (lbs)"),
    ("right_leg", "Right Leg (lbs)"),
    ("left_leg", "Left Leg (lbs)"),
    ("basal_metabolic_weight", "Basal Metabolic Weight"),
]

# Shown in the "change since first entry" line under the history list
PROGRESS = [("weight", "Weight", "lbs"), ("skeletal_muscle_mass", "Muscle", "lbs"), ("percent_body_fat", "Body fat", "%")]


# --- Turning measurements into a body shape ---
# These are rough modelling choices, not medical facts. Change them to taste.

BODY = "wireBody_grp"
SHAPE_NODES = ["wireBody_skin_shapes", "wireBody_wires_shapes"]

# The measurements the neutral wire body is treated as having
NEUTRAL = {"height_in": 70.2, "body_fat_mass": 28.0,
           "trunk": 58.0, "right_arm": 7.5, "left_arm": 7.5, "right_leg": 20.5, "left_leg": 20.5}
# The share of total body fat assumed to sit on each part (the rest is head, hands and feet)
FAT_SHARE = {"trunk": 0.50, "right_arm": 0.05, "left_arm": 0.05, "right_leg": 0.17, "left_leg": 0.17}
NEUTRAL_SHAPE = dict({part: 1.0 for part in FAT_SHARE}, height=1.0)
THINNEST, THICKEST = 0.5, 2.5  # limits so odd numbers can't turn the body inside out


def entry_shape(entry):
    """How an entry compares with the neutral body: 1.0 means the same, 1.1 means 10% taller or thicker.

    A part's thickness comes from its mass (its lean pounds plus its share of the body fat).
    Mass is spread along the part's length, so for the same mass a taller person is thinner.
    """
    tall = (entry.get("height_in") or NEUTRAL["height_in"]) / NEUTRAL["height_in"]
    shape = {"height": tall}
    for part, share in FAT_SHARE.items():
        lean = entry.get(part, 0.0)
        if lean <= 0:  # not filled in
            shape[part] = 1.0
            continue
        mass = lean + share * entry.get("body_fat_mass", 0.0)
        neutral_mass = NEUTRAL[part] + share * NEUTRAL["body_fat_mass"]
        shape[part] = math.sqrt(mass / neutral_mass / tall ** 3)
    return shape


def shape_at(entries, position, exaggerate):
    """The body shape at a slider position: 0 is neutral, 1 the first entry, 2 the second, and so on.

    Positions in between blend the neighbouring shapes. Changes after the first entry are
    multiplied up by `exaggerate`, because real changes between weigh-ins are too small to see.
    """
    if not entries:
        return dict(NEUTRAL_SHAPE)
    true_shapes = [entry_shape(e) for e in entries]
    first = true_shapes[0]
    stops = [NEUTRAL_SHAPE] + [{key: first[key] * (shape[key] / first[key]) ** exaggerate for key in shape}
                               for shape in true_shapes]
    position = max(0.0, min(float(len(entries)), position))
    before = min(int(position), len(stops) - 1)
    after = min(before + 1, len(stops) - 1)
    blend = position - before
    return {key: stops[before][key] + (stops[after][key] - stops[before][key]) * blend for key in NEUTRAL_SHAPE}


def body_ready():
    return cmds.objExists(BODY) and all(cmds.objExists(node) for node in SHAPE_NODES)


def pose_body(shape):
    """Reshape the wire body in the scene. Returns False if there is no adjustable body to reshape."""
    if not body_ready():
        return False
    cmds.undoInfo(stateWithoutFlush=False)  # keep slider drags out of Maya's undo list
    try:
        for part in FAT_SHARE:
            thickness = max(THINNEST, min(THICKEST, shape[part]))
            for node in SHAPE_NODES:
                cmds.setAttr(node + "." + part, thickness - 1.0)
        cmds.setAttr(BODY + ".scale", shape["height"], shape["height"], shape["height"])
    finally:
        cmds.undoInfo(stateWithoutFlush=True)
    return True


# --- Saved files ---

def profile_path(name):
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    return os.path.join(PROFILE_DIR, safe + ".json")


def list_profiles():
    """Names of everyone with a saved profile, in alphabetical order."""
    names = []
    if os.path.isdir(PROFILE_DIR):
        for filename in os.listdir(PROFILE_DIR):
            if filename.endswith(".json"):
                with open(os.path.join(PROFILE_DIR, filename)) as f:
                    names.append(json.load(f)["name"])
    return sorted(names, key=str.lower)


def load_profile(name):
    path = profile_path(name)
    if not os.path.exists(path):
        return {"name": name.strip(), "entries": []}
    with open(path) as f:
        return json.load(f)


def write_profile(profile):
    path = profile_path(profile["name"])
    if not profile["entries"]:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(PROFILE_DIR, exist_ok=True)
    profile["entries"].sort(key=lambda entry: entry["date"])
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)


def store_entry(name, entry):
    """Add an entry to a person's profile, replacing any entry with the same date."""
    profile = load_profile(name)
    profile["entries"] = [e for e in profile["entries"] if e["date"] != entry["date"]]
    profile["entries"].append(entry)
    write_profile(profile)


def remove_entry(name, date):
    profile = load_profile(name)
    profile["entries"] = [e for e in profile["entries"] if e["date"] != date]
    write_profile(profile)


# --- Window ---

class BodyProfileWindow:
    def __init__(self):
        self.fields = {}
        self.history_dates = []
        self.build()
        self.refresh_profile_menu()
        self.new_entry()
        self.refresh_slider()

    def build(self):
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        cmds.window(WINDOW, title="Wire Body Profile", sizeable=True)
        cmds.scrollLayout(childResizable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))

        cmds.frameLayout(label="Profile", marginHeight=6, marginWidth=4)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
        self.profile_menu = cmds.optionMenuGrp(label="Saved profiles", changeCommand=self.on_profile_chosen,
                                               columnWidth=(1, 170))
        self.name_field = cmds.textFieldGrp(label="Name", columnWidth=(1, 170), adjustableColumn=2)
        self.date_field = cmds.textFieldGrp(label="Date (YYYY-MM-DD)", columnWidth=(1, 170), adjustableColumn=2)
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.frameLayout(label="Measurements", marginHeight=6, marginWidth=4)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
        self.height_field = cmds.floatFieldGrp(label="Height (ft, in)", numberOfFields=2, precision=1,
                                               columnWidth=(1, 170))
        # Two columns, reading down the left one first, to keep the window short
        cmds.rowColumnLayout(numberOfColumns=2)
        half = (len(MEASUREMENTS) + 1) // 2
        for left, right in zip(MEASUREMENTS[:half], MEASUREMENTS[half:]):
            for key, label in (left, right):
                self.fields[key] = cmds.floatFieldGrp(label=label, numberOfFields=1, precision=1,
                                                      columnWidth=((1, 170), (2, 70)))
        cmds.setParent("..")
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnAttach=((1, "both", 0), (2, "both", 4)))
        cmds.button(label="Save Entry", height=30, command=self.on_save)
        cmds.button(label="New Entry", height=30, width=110, command=self.new_entry)
        cmds.setParent("..")
        self.status = cmds.text(label="", align="left")

        cmds.frameLayout(label="History (click an entry to load it)", marginHeight=6, marginWidth=4)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        self.history = cmds.textScrollList(numberOfRows=5, allowMultiSelection=False, font="fixedWidthFont",
                                           selectCommand=self.on_history_chosen)
        self.progress = cmds.text(label="", align="left")
        cmds.button(label="Delete Selected Entry", command=self.on_delete)
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.frameLayout(label="Wire body over time", marginHeight=6, marginWidth=4)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        self.slider = cmds.floatSliderGrp(label="Entry (0 = neutral)", field=True, minValue=0, maxValue=1, value=0,
                                          step=0.01, precision=2, columnWidth=((1, 170), (2, 50)),
                                          adjustableColumn=3, dragCommand=self.on_slider, changeCommand=self.on_slider)
        self.slider_note = cmds.text(label="", align="left")
        self.exaggerate = cmds.floatSliderGrp(label="Exaggerate change x", field=True, minValue=1, maxValue=10, value=4,
                                              step=0.5, precision=1, columnWidth=((1, 170), (2, 50)),
                                              adjustableColumn=3, dragCommand=self.on_slider,
                                              changeCommand=self.on_slider)
        cmds.button(label="Rebuild Wire Body", command=self.on_rebuild)
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.showWindow(WINDOW)
        cmds.window(WINDOW, edit=True, widthHeight=(540, 700))

    # Reading and filling the fields

    def name(self):
        return cmds.textFieldGrp(self.name_field, query=True, text=True).strip()

    def read_entry(self):
        feet, inches = cmds.floatFieldGrp(self.height_field, query=True, value=True)
        entry = {"date": cmds.textFieldGrp(self.date_field, query=True, text=True).strip(),
                 "height_in": round(feet * 12 + inches, 1)}
        for key, _ in MEASUREMENTS:
            entry[key] = round(cmds.floatFieldGrp(self.fields[key], query=True, value1=True), 1)
        return entry

    def fill_entry(self, entry):
        cmds.textFieldGrp(self.date_field, edit=True, text=entry["date"])
        self.fill_height(entry.get("height_in", 0.0))
        for key, _ in MEASUREMENTS:
            cmds.floatFieldGrp(self.fields[key], edit=True, value1=entry.get(key, 0.0))

    def fill_height(self, height_in):
        feet = int(height_in // 12)
        cmds.floatFieldGrp(self.height_field, edit=True, value1=feet, value2=round(height_in - feet * 12, 1))

    def new_entry(self, *_):
        """Blank measurements dated today. Keeps the name, and the height from the latest entry."""
        entries = load_profile(self.name())["entries"] if self.name() else []
        blank = {"date": datetime.date.today().isoformat(), "height_in": entries[-1]["height_in"] if entries else 0.0}
        self.fill_entry(blank)
        cmds.textScrollList(self.history, edit=True, deselectAll=True)
        self.say("")

    def say(self, message):
        cmds.text(self.status, edit=True, label=message)

    # Lists

    def refresh_profile_menu(self, select=None):
        menu = self.profile_menu + "|OptionMenu"
        for item in cmds.optionMenu(menu, query=True, itemListLong=True) or []:
            cmds.deleteUI(item)
        for label in [NEW_PROFILE] + list_profiles():
            cmds.menuItem(label=label, parent=menu)
        if select in list_profiles():
            cmds.optionMenuGrp(self.profile_menu, edit=True, value=select)

    def refresh_history(self):
        entries = load_profile(self.name())["entries"] if self.name() else []
        self.history_dates = [e["date"] for e in reversed(entries)]  # newest first
        cmds.textScrollList(self.history, edit=True, removeAll=True)
        for e in reversed(entries):
            cmds.textScrollList(self.history, edit=True, append="%s   %6.1f lbs   muscle %5.1f   fat %4.1f%%" % (
                e["date"], e["weight"], e["skeletal_muscle_mass"], e["percent_body_fat"]))

        summary = ""
        if len(entries) > 1:
            first, last = entries[0], entries[-1]
            changes = ["%s %+.1f %s" % (label, last[key] - first[key], unit) for key, label, unit in PROGRESS]
            summary = "Since %s:  %s" % (first["date"], ",  ".join(changes))
        cmds.text(self.progress, edit=True, label=summary)

    # Wire body slider

    def entries(self):
        return load_profile(self.name())["entries"] if self.name() else []

    def refresh_slider(self, position=None):
        """Match the slider to the current profile: it runs from 0 to the number of saved entries."""
        count = len(self.entries())
        if position is None:
            position = count  # the latest entry
        cmds.floatSliderGrp(self.slider, edit=True, enable=count > 0, maxValue=max(count, 1),
                            fieldMaxValue=max(count, 1), value=min(position, count))
        self.on_slider()

    def on_slider(self, *_):
        entries = self.entries()
        position = cmds.floatSliderGrp(self.slider, query=True, value=True) if entries else 0.0
        exaggerate = cmds.floatSliderGrp(self.exaggerate, query=True, value=True)
        found = pose_body(shape_at(entries, position, exaggerate))

        nearest = int(round(position))
        if not found:
            note = "No adjustable wire body in the scene. Click Rebuild Wire Body."
        elif not entries:
            note = "Neutral body. Save an entry to see it change."
        elif abs(position - nearest) > 0.005:
            earlier = "neutral" if int(position) == 0 else entries[int(position) - 1]["date"]
            note = "Between %s and %s" % (earlier, entries[int(position)]["date"])
        elif nearest == 0:
            note = "Neutral body, before any measurements"
        else:
            entry = entries[nearest - 1]
            note = "Entry %d of %d:  %s,  %.1f lbs" % (nearest, len(entries), entry["date"], entry["weight"])
        cmds.text(self.slider_note, edit=True, label=note)

    def on_rebuild(self, *_):
        if cmds.objExists(BODY):
            answer = cmds.confirmDialog(title="Rebuild wire body?", button=["Rebuild", "Cancel"], cancelButton="Cancel",
                                        defaultButton="Cancel", dismissString="Cancel",
                                        message="This deletes the wire body in the scene and builds a fresh one.")
            if answer != "Rebuild":
                return
        import build_wire_body
        importlib.reload(build_wire_body)
        build_wire_body.build()
        self.on_slider()

    # Buttons and menus

    def on_profile_chosen(self, choice):
        cmds.textFieldGrp(self.name_field, edit=True, text="" if choice == NEW_PROFILE else choice)
        self.refresh_history()
        self.new_entry()
        self.refresh_slider()

    def on_history_chosen(self, *_):
        picked = cmds.textScrollList(self.history, query=True, selectIndexedItem=True)
        if picked:
            date = self.history_dates[picked[0] - 1]
            entry = next(e for e in load_profile(self.name())["entries"] if e["date"] == date)
            self.fill_entry(entry)
            self.say("Showing the entry from " + date)
            self.refresh_slider(position=len(self.history_dates) - picked[0] + 1)

    def on_save(self, *_):
        name, entry = self.name(), self.read_entry()
        if not name:
            self.say("Type a name before saving.")
            return
        try:
            datetime.date.fromisoformat(entry["date"])
        except ValueError:
            self.say("The date needs to look like 2026-10-06.")
            return
        if any(e["date"] == entry["date"] for e in load_profile(name)["entries"]):
            answer = cmds.confirmDialog(title="Replace entry?", button=["Replace", "Cancel"], cancelButton="Cancel",
                                        defaultButton="Cancel", dismissString="Cancel",
                                        message="%s already has an entry for %s. Replace it?" % (name, entry["date"]))
            if answer != "Replace":
                return
        store_entry(name, entry)
        self.refresh_profile_menu(select=name)
        self.refresh_history()
        self.refresh_slider(position=len(self.history_dates) - self.history_dates.index(entry["date"]))
        self.say("Saved %s for %s." % (entry["date"], name))

    def on_delete(self, *_):
        picked = cmds.textScrollList(self.history, query=True, selectIndexedItem=True)
        if not picked:
            self.say("Click an entry in the history list first.")
            return
        name, date = self.name(), self.history_dates[picked[0] - 1]
        answer = cmds.confirmDialog(title="Delete entry?", button=["Delete", "Cancel"], cancelButton="Cancel",
                                    defaultButton="Cancel", dismissString="Cancel",
                                    message="Delete the %s entry for %s? This can't be undone." % (date, name))
        if answer != "Delete":
            return
        remove_entry(name, date)
        self.refresh_profile_menu(select=name)
        self.refresh_history()
        self.refresh_slider()
        self.say("Deleted the %s entry." % date)


def show():
    global window
    window = BodyProfileWindow()
    return window
