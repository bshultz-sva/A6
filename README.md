# A6: Wire Body Profile (InBody Data Build)

A blue wire-frame human figure in Maya, plus a **Wire Body Profile** window. You type in a set of body-composition measurements (the same list as an InBody printout), save them under a person's name and a date, and come back later to add more dated entries. A slider then reshapes the wire body across the saved entries, so you can watch the changes over time.

![The wire body](wire_body/preview.png)

## Which app

**Autodesk Maya 2027** (tested on macOS). The tool is a Python script that runs inside Maya; nothing else needs to be installed.

The scene file was saved in Maya 2027, so older versions of Maya can't open it.

## Install

1. Download this repo: click the green **Code** button, then **Download ZIP**, and unzip it. Or clone it:
   ```
   git clone https://github.com/bshultz-sva/A6.git
   ```
2. Keep the files together. `InBody Data Build.mb` and the `wire_body` folder must stay side by side, because the scene looks for the code in the `wire_body` folder next to it.

## Run

1. Open Maya 2027.
2. **File > Open Scene...** and choose `InBody Data Build.mb`.
3. The **Wire Body Profile** window is meant to open by itself once the scene has loaded. If Maya asks whether to allow the scripts in the scene to run, say yes, because that script is what opens the window.

**If the window doesn't appear** (this happened in the peer test below), open it by hand: go to **Windows > General Editors > Script Editor**, click the **Python** tab, paste this, change the path to where you put the repo, and press Ctrl+Enter (or Cmd+Enter):

```python
import sys
sys.path.insert(0, "/path/to/A6/wire_body")
import body_profile_ui
body_profile_ui.show()
```

## Using the window

- **Profile:** pick a saved person from **Saved profiles**, or choose **New profile...** and type a **Name**. The **Date** is filled in as today (YYYY-MM-DD).
- **Measurements:** fill in height and any of the measurements (weight, body fat mass, skeletal muscle mass, the lean mass of each arm, leg and the trunk, and so on). Blank fields are fine.
- **Save Entry** stores the entry. **New Entry** clears the form for another date.
- **History:** click an entry to load it back into the form. **Delete Selected Entry** removes it. The line under the list shows the change since the first entry.
- **Wire body over time:** the **Entry** slider goes from 0 (the neutral body) through each saved entry in date order, and the figure's height and the thickness of its trunk, arms and legs follow the numbers. **Exaggerate change** multiplies the differences between entries (4x by default), because real changes between weigh-ins are too small to see.
- **Rebuild Wire Body** builds the figure again from scratch if it was deleted or broken.

![The slider reshaping the body](wire_body/slider_preview.png)

Profiles are saved as one JSON file per person in `~/Documents/wire_body/profiles` (the folder is created the first time you save). They stay on your own computer, not in this repo.

The way measurements turn into a body shape is a rough artistic model, not a medical one. The numbers it uses are at the top of `body_profile_ui.py`.

## What works now, and what doesn't yet

**Works** (confirmed in the peer run below):
- Saving dated entries under a person's name, loading them back from the history list, and deleting them.
- **Rebuild Wire Body**, which regenerates the figure (2196 triangles, about 179 cm tall).
- The **Entry** slider, which reshapes the body's height and the thickness of its trunk, arms and legs from the neutral body through each dated entry, and the **Exaggerate change** multiplier.

**Doesn't work yet / limits:**
- **The window doesn't reliably open on its own when the scene loads.** On the classmate's computer it didn't open, and it had to be started by hand with the Script Editor code above. The cause isn't confirmed. A likely one is Maya 2027's security settings (**Preferences > Security**, including Safe Mode), which can stop scripts saved inside a scene from running. Opening the window by hand always works.
- **Maya 2027 only.** The scene was saved in Maya 2027, so older versions of Maya can't open it.

## Peer run

**Irene Kao** cloned the repo and tested it in Maya 2027:

1. I cloned the repo, opened `InBody Data Build.mb` in Maya 2027, launched the window, and entered three dated measurements for a test profile so the wire body had something to follow.
2. Everything in the README worked as described — Save Entry stored the entries, the history list loaded them back, Delete Selected Entry removed one, Rebuild Wire Body regenerated the figure (2196 triangles, 179 cm tall), and the Entry slider smoothly reshaped the wire body's height and limb/trunk thickness from the neutral body through each dated entry, with the "Exaggerate change" multiplier doing its job.
3. The only thing that tripped me up was that the window didn't open automatically when the scene loaded (I had to run `import body_profile_ui; body_profile_ui.show()` by hand), and the tool requires Maya 2027 specifically since the scene was saved in that version — but once it was open I could not get anything to actually break.

## Files

| File | What it is |
| --- | --- |
| `InBody Data Build.mb` | The Maya scene with the wire body, set to open the window on load |
| `wire_body/body_profile_ui.py` | The Wire Body Profile window |
| `wire_body/build_wire_body.py` | Builds the wire body in the open scene from `body_lowpoly.obj` (used by **Rebuild Wire Body**) |
| `wire_body/body_lowpoly.obj`, `body_highres.obj` | The body shape the wire frame is made from |
| `wire_body/make_body_shape.py` | Optional: sculpts the body shape and rewrites the two .obj files. Runs outside Maya and needs `pip install numpy scipy scikit-image`. You only need it to change the base body. |
