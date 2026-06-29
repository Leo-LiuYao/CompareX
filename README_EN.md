<p align="center">
  <img src="assets/comparex_icon.png" alt="CompareX" width="96" height="96">
</p>

<h1 align="center">CompareX</h1>

<p align="center">
  A desktop tool for detailed image comparison in computer vision research.<br>
  Line up inputs, GT, and model outputs; inspect pixels; export evidence.
</p>

<p align="center">
  <a href="README.md">中文说明</a> · Python 3.10+ · PyQt6 Fluent · Local processing
</p>

<img src="assets/comparex_banner.png" alt="CompareX multi-folder preview page" width="100%">

## Why it exists

In visual experiments, the slow part is often not opening images. It is answering questions like:

- Are the same samples aligned across multiple result folders?
- Is one model only better in a tiny local region?
- Are brightness, color shifts, texture, edges, and artifacts actually different?
- Do PSNR / SSIM numbers match what the eye sees?
- Which examples are worth using in a paper figure or ablation section?

General image viewers are good at browsing. CompareX is built for the comparison workflow around research outputs: lightweight, offline, local, and focused on checking experimental results quickly.

<img src="assets/comparex_workflow.png" alt="CompareX compare window with eyedropper, diff map, and local zoom" width="100%">

## Who it is for

- Researchers working on HDR, low-light enhancement, denoising, super-resolution, deblurring, reconstruction, rendering, or segmentation visualization
- Anyone who repeatedly compares `input / gt / method A / method B / method C`
- People selecting images for papers, supplements, experiment logs, or internal reports
- Users who prefer a local tool instead of uploading experimental images to web services

## What it can do

### Multi-folder browsing

- Drag or open up to 12 folders
- Switch between single-folder and multi-folder grid views
- Align rows by filename or by folder order
- Scale thumbnails, search, select, rotate, and use context menus
- Save, restore, and browse workspace history

### Compare window

- Side-by-side columns with linked zoom and pan
- Mouse wheel and trackpad pinch zoom; `R` resets the view
- `Space` for next row, `B` for previous row, hold `Tab` to preview the next column
- Metadata overlays: folder, filename, resolution, file size, zoom level
- macOS native fullscreen; `Esc` exits fullscreen

### Detail inspection

- **Eyedropper**: synced RGB / HEX sampling across columns
- **Pixel RGB**: pixel grid and RGB labels at high zoom
- **Crop export**: `Shift + drag` to export rect / square / circle crops
- **Histogram**: compare RGB distributions across images

### Difference and metrics

- **Diff map**: Euclidean distance, L1, MSE, absolute difference, max channel difference
- **Color view**: RGB / BGR / RBG / GRB / GBR / BRG channel orders
- **Display modes**: color, R only, G only, B only, luminance Y
- **Brightness / contrast / gamma**: display-only adjustments; original files are not modified
- **PSNR / SSIM**: choose a baseline column, overlay metrics, export wide-table CSV

### Extension tools

- Built-in custom Python tool panel
- Choose target columns, run, revert, and manage tools
- Useful for quick edge detection, mask visualization, or temporary experiment checks

## Quick start

```bash
cd CompareX
pip install -r requirements.txt
python main.py
```

If PyPI is unavailable in an internal environment, install the PyQt6 version of PyQt-Fluent-Widgets from an official/local source.

Config and cache directory:

```text
~/.imagecompare_fluent/
```

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl/⌘ + O` | Open folder |
| `Ctrl/⌘ + M` | Toggle single / multi-folder mode |
| `Space` | Open compare / next row |
| `B` | Previous row |
| `Tab` | Hold to preview next column |
| `R` | Reset zoom and pan |
| `Shift + drag` | Select crop region |
| `Backspace` | Remove the current compare column's folder |

## Build macOS DMG

Do not run PyInstaller directly from a conda base environment. It can bundle unrelated libraries such as torch and transformers, making the app huge and sometimes breaking OpenCV at startup.

Use the project script:

```bash
cd CompareX
bash scripts/build_mac.sh
```

Outputs:

```text
dist/CompareX.app
dist/CompareX.dmg
```

If macOS blocks the first launch, right-click `CompareX.app` and choose **Open**.

## Notes

- CompareX is a personal utility designed around computer vision experiment review
- All image processing runs locally
- The canvas and thumbnail grid are custom-painted; controls use PyQt6-Fluent-Widgets
- Maintenance follows the author's own research needs
