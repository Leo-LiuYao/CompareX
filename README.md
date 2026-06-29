<p align="center">
  <img src="assets/comparex_icon.png" alt="CompareX" width="96" height="96">
</p>

<h1 align="center">CompareX</h1>

<p align="center">
  面向计算机视觉科研人员的图片细节对比工具。<br>
  把原图、GT、不同模型输出放在同一行里看清楚、量清楚、导出来。
</p>

<p align="center">
  <a href="README_EN.md">English</a> ·
  Python 3.10+ · PyQt6 Fluent · 本地运行
</p>

<img src="assets/comparex_banner.png" alt="CompareX 多文件夹预览页" width="100%">

## 为什么需要它

做视觉实验时，真正费时间的往往不是打开图片，而是反复确认这些细节：

- 同一个样本在多个结果文件夹里是否**对齐**
- 某个模型是否只在局部区域更好
- 亮度、色偏、边缘、纹理、伪影到底差在哪里
- PSNR / SSIM 高低是否和肉眼观感一致
- 写论文或做 ablation 前，哪几组图最值得拿出来展示

通用看图软件能浏览图片，但很少把这些动作做成一个顺手的科研工作流。CompareX 就是为这个场景做的：轻量、离线、本地处理，偏向“快速检查实验结果”，不是图库管理器，也不是大型标注平台。

<img src="assets/comparex_workflow.png" alt="CompareX 对比窗口：吸管、差异图与局部放大" width="100%">

## 适合谁

- 做 HDR、低光增强、去噪、超分、去模糊、重建、渲染、分割可视化等任务的研究人员
- 需要同时查看 `input / gt / method A / method B / method C` 的同学
- 需要在论文图、补充材料、实验记录前快速筛图的人
- 想要一个本地小工具，而不是把图片上传到网页服务的人

## 功能一览

### 多文件夹对齐浏览

- 支持拖入或选择多个文件夹，最多 12 列
- 支持单文件夹模式 / 多文件夹模式
- 多文件夹下可按**文件名对齐**或按**顺序对齐**
- 缩略图大小可调，支持搜索、选中、旋转、右键菜单
- 工作区保存、恢复、历史记录，适合连续几天看同一批实验

### 对比窗口

- 多列并排显示，同步缩放和平移
- 鼠标滚轮、触控板捏合缩放，`R` 重置视图
- `Space` 下一行，`B` 上一行，长按 `Tab` 临时预览下一列
- 显示文件夹、文件名、分辨率、文件大小、缩放比例等信息
- 支持 macOS 原生全屏，`Esc` 退出全屏

### 细节检查

- **吸管**：鼠标位置同步取样，比较多列 RGB / HEX
- **像素 RGB**：高倍缩放后显示像素网格和 RGB 标注
- **裁剪导出**：`Shift + 拖拽` 选择矩形 / 正方形 / 圆形区域并批量导出
- **直方图**：查看多图 RGB 分布差异

### 差异与指标

- **差异图**：欧式距离、L1、MSE、绝对差、通道最大差
- **色彩查看**：RGB / BGR / RBG / GRB / GBR / BRG 通道顺序
- **显示模式**：彩色、仅 R、仅 G、仅 B、亮度 Y
- **亮度 / 对比度 / Gamma**：只影响显示，不写回原图
- **PSNR / SSIM**：选择基准列，图上标注，并导出宽表 CSV

### 扩展工具

- 内置自定义 Python 工具面板
- 可选择作用列、运行、撤回、管理工具
- 适合放一些临时检查脚本，例如边缘检测、mask 可视化、调试型预处理

## 快速开始

```bash
cd CompareX
pip install -r requirements.txt
python main.py
```

如果内网无法访问 PyPI，可以从官方源码或本地缓存安装 PyQt6-Fluent-Widgets 的 PyQt6 版本。

配置与缓存目录：

```text
~/.imagecompare_fluent/
```

## 常用快捷键

| 快捷键 | 作用 |
|---|---|
| `Ctrl/⌘ + O` | 打开文件夹 |
| `Ctrl/⌘ + M` | 切换单 / 多文件夹模式 |
| `Space` | 打开对比 / 下一行 |
| `B` | 上一行 |
| `Tab` | 长按预览下一列 |
| `R` | 重置缩放和平移 |
| `Shift + 拖拽` | 框选裁剪区域 |
| `Backspace` | 在对比页移除当前列对应文件夹 |

## 打包 macOS DMG

不要在 conda 主环境里直接运行 PyInstaller，否则容易把 torch、transformers 等无关库打进包，体积会非常大，还可能导致 OpenCV 启动失败。

使用项目脚本打包：

```bash
cd CompareX
bash scripts/build_mac.sh
```

产物：

```text
dist/CompareX.app
dist/CompareX.dmg
```

首次打开若被 macOS 拦截，请右键 `CompareX.app`，选择“打开”。

## 说明

- CompareX 是自用工具，功能优先服务计算机视觉实验结果检查
- 图片处理均在本地完成
- 画布和缩略图网格为自绘，控件层使用 PyQt6-Fluent-Widgets
- 当前维护节奏以作者自用需求为主
