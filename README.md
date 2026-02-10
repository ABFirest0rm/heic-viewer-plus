# HeicViewerPlus

> **A fast, modern image viewer for Windows and Linux.**  
> View, crop, rotate, and convert modern image formats — with first-class HEIC support on Windows.

[![Download](https://img.shields.io/github/v/release/ABFirest0rm/heic-viewer-plus?label=Download&style=for-the-badge)](https://github.com/ABFirest0rm/heic-viewer-plus/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-blue?style=for-the-badge)](https://github.com/ABFirest0rm/heic-viewer-plus/releases)



<img width="2560" height="1600" alt="01_main_view" src="https://github.com/user-attachments/assets/5c87a430-3c54-416b-b348-bfc51570ef96" />

---

## 🚀 Why HeicViewerPlus?

While Windows supports formats like AVIF and WebP, support for **HEIC** (widely used by modern smartphones) is inconsistent and often requires paid extensions or file conversions.

**HeicViewerPlus** is a lightweight, standalone **viewer-plus** tool designed to fix this gap.
It opens modern image formats instantly, lets you view images and preview edits such as crop and rotation, and only writes to disk when you explicitly choose **Save As**.

---

## ✨ Features

- **Broad Format Support:** `.heic`, `.heif`, `.avif`, `.webp`, `.jpg`, `.png`, `.tif`, `.bmp`, `.ico`
- **⚡ Asymmetric Predictive Caching:** A background preloading engine predicts navigation direction and buffers upcoming images for near zero-latency browsing
- **Viewer + Editor:** View images, crop, rotate, flip, and export — all in one lightweight tool
- **Non-Destructive Workflow:** All edits are applied as **view transforms**; the original file is never modified until you click **Save As**
- **Lightweight Undo / Redo:** Instantly undo or redo crops and rotations without reloading image data
- **Smart Zoom:** Dedicated **1:1 Pixel Mode** (`Ctrl+F`) for checking focus and sharpness
- **Conversion & Export:** Save edited images as **JPEG, PNG, WebP, HEIC, or AVIF**
- **EXIF Metadata Display:** Dimensions, file size, date, camera make/model shown in the status bar

---

## ⚙️ Under the Hood

HeicViewerPlus is built with **PySide6 (Qt)** and **Pillow**, with a strong focus on performance and responsiveness:

- **Multi-threaded Pipeline:** Uses `QThreadPool` to move file I/O and decoding off the GUI thread, keeping the interface responsive even for 50MB+ HEIC files
- **Asymmetric Predictive Caching:** The preload radius is biased based on navigation direction (forward vs backward), prioritizing the images you are most likely to view next instead of loading symmetrically
- **Memory-Bound Asymmetric Window:** The cache maintains a direction-biased sliding window instead of a fixed radius, preventing memory growth while prioritizing the most likely next images

- **Affine View Transforms:** Zoom, rotation, and crop previews rely on Qt’s graphics-view transformations instead of mutating pixel buffers, ensuring zero quality loss during viewing

---

## 📥 Download & Run

**No installation required.** Portable binaries are available on the Releases page.

### 🪟 Windows
1. [Download the latest `.exe`](https://github.com/ABFirest0rm/heic-viewer-plus/releases/latest)
2. Double-click to run
3. *(Optional)* Right-click a `.HEIC` file → **Open with** → Select `HeicViewerPlus.exe` to make it your default viewer

> **Note:** Windows SmartScreen may appear for new apps.  
> Click **More info → Run anyway**.

---

### 🐧 Linux
1. [Download the binary](https://github.com/ABFirest0rm/heic-viewer-plus/releases/latest)
2. Mark it executable and run:
   ```bash
   chmod +x HeicViewerPlus-Linux-x86_64
   ./HeicViewerPlus-Linux-x86_64
