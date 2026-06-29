<div align="center">
  <img src="assets/comparex_icon.png" alt="CompareX" width="120" height="120">

  <h1>🔍 CompareX</h1>

  <p><b>A lightweight, efficient local image comparison and metric analysis personal utility.</b></p>

  <p>
    <a href="README.md">中文说明</a> ·
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/PyQt6-Fluent_Widgets-green.svg" alt="PyQt6">
    <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey.svg" alt="Platform">
  </p>
</div>

<br>

<img src="assets/comparex_banner.png" alt="CompareX Multi-folder Preview" width="100%" style="border-radius: 8px;">

## 💡 Why it exists

In visual experiments, the slow part is often not opening images. It is answering questions like:

- 🧐 Are the same samples **strictly aligned** across multiple result folders?
- 🎯 Is one model only better in a tiny local region (e.g., edges, dark areas)?
- 🎨 Are brightness, color shifts, texture, edges, and artifacts actually different?
- 📊 Do PSNR / SSIM numbers match what the human eye sees?
- 📝 Which examples are worth using in a paper figure or ablation section?

General image viewers are good at browsing, but lack synced multi-folder comparison, pixel-level inspection, and quantitative metrics. **CompareX** is a personal utility that integrates the best features of multiple image comparison tools. It is lightweight, offline, local, and focused on checking experimental results quickly. Updates are casual and at-will.

<img src="assets/comparex_workflow.png" alt="CompareX Compare Window" width="100%" style="border-radius: 8px;">

---

## 👥 Who is it for?

- 🔬 Researchers working on HDR, low-light enhancement, denoising, super-resolution, deblurring, reconstruction, rendering, or segmentation visualization.
- 📁 Anyone who repeatedly compares `input / gt / method A / method B / method C`.
- 🖼️ People selecting images for papers, supplements, experiment logs, or internal reports.
- 🔒 Users who prefer a purely local tool instead of uploading sensitive experimental images to web services.

---

## ✨ Key Features

### 🗂️ Multi-folder Browsing
- **Seamless Loading**: Drag or open up to 12 folders side-by-side.
- **Flexible Alignment**: Align rows by filename or by folder order.
- **Workspace History**: Automatically saves workspace state and supports restoring history, perfect for reviewing the same batch of experiments over several days.

### 🔍 Immersive Compare Window
- **Synced Zoom & Pan**: Side-by-side columns with perfectly linked mouse wheel and trackpad pinch zoom.
- **Quick Navigation**: `Space` for next row, `B` for previous row, hold `Tab` to temporarily preview the next column.
- **Metadata Overlay**: Clearly displays folder, filename, resolution, file size, and zoom level.

### 🔬 Pixel-level Inspection
- **Eyedropper**: Synced RGB / HEX sampling across all columns.
- **Pixel Grid**: Displays pixel grid and exact RGB labels at high zoom levels.
- **Crop Export**: `Shift + drag` to select and batch-export rect / square / circle crop regions.
- **Histogram**: One-click comparison of RGB distributions across images.

### 📈 Differences & Metrics
- **Diff Map**: Visualize Euclidean distance, L1, MSE, absolute difference, and max channel difference.
- **Color Space**: Switch between RGB / BGR / RBG / GRB / GBR / BRG channel orders.
- **Real-time Adjustments**: Tweak brightness / contrast / gamma (display-only, original files are unmodified).
- **Metrics**: Select a baseline column to calculate and overlay **PSNR / SSIM**, and export results as a CSV table.

### 🛠️ Extension Tools
- **Python Scripts**: Built-in custom Python tool panel, ideal for temporary inspection scripts like edge detection or mask visualization.

---

## 🚀 Quick Start

```bash
# Clone or download the code, then enter the directory
cd CompareX

# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py
```

> **Note**: Config and cache directories are located at `~/.imagecompare_fluent/` by default.

---

## ⌨️ Shortcuts

| Shortcut | Action |
|:---|:---|
| <kbd>Ctrl/⌘</kbd> + <kbd>O</kbd> | Open folder |
| <kbd>Ctrl/⌘</kbd> + <kbd>M</kbd> | Toggle single / multi-folder mode |
| <kbd>Space</kbd> | Open compare / next row |
| <kbd>B</kbd> | Previous row |
| <kbd>Tab</kbd> (Hold) | Preview next column |
| <kbd>R</kbd> | Reset zoom and pan |
| <kbd>Shift</kbd> + drag | Select crop region |
| <kbd>Backspace</kbd> | Remove the current compare column's folder |

---

## 📦 Build macOS DMG

> ⚠️ **Warning**: Do not run PyInstaller directly from a conda base environment. It can bundle unrelated libraries (like torch, transformers), making the app huge and potentially breaking OpenCV at startup.

Use the provided lean build script:

```bash
cd CompareX
bash scripts/build_mac.sh
```

Outputs will be generated in the `dist/` directory:
- `dist/CompareX.app`
- `dist/CompareX.dmg`

*(If macOS blocks the first launch, right-click `CompareX.app` and choose **Open**)*

---

## 📌 Notes

- CompareX is purely a personal utility. Updates and maintenance are casual and at-will, primarily serving the author's own experiment review needs.
- All image processing runs locally; no data is uploaded.
- The canvas and thumbnail grid are custom-painted; UI controls use [PyQt6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets).
