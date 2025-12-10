# Python does analysis, frontend does rendering with Canvas


1. Data shape & encoding
2. Python backend (API design + code sketch)
3. Vue frontend (fetch, canvas rendering, zoom/pan, tooltips)
4. Performance notes & variants

---

## 1. Data model

For one video, you have:

* `frame_count` = ~15000  → x-axis
* `point_count` = 30      → y-axis
* Values: `values[frame][point]` (float or int) → color

We’ll send:

* Binary matrix in **row-major**: `[frame0: p0..p29, frame1: p0..p29, …]`
* A tiny JSON “header” saying how to interpret it.

Example concept:

```json
{
  "width": 15000,      // frames
  "height": 30,        // points
  "dtype": "float32",
  "min": 0.0,
  "max": 1.0
}
```

Matrix bytes are sent as `width * height * 4` bytes (float32).

---

## 2. Python backend

### 2.1 Data preparation

Assume you already have a NumPy array from your OpenCV pipeline:

```python
import numpy as np

# shape: (frame_count, point_count)
values = np.random.rand(15000, 30).astype(np.float32)  # example
frame_count, point_count = values.shape

data_min = float(values.min())
data_max = float(values.max())
```

Store it somewhere (cache, db, file) keyed by video id.

### 2.2 API design

You need at least:

1. `GET /video/<id>/heatmap/meta` → JSON header
2. `GET /video/<id>/heatmap/raw` → binary matrix bytes

You can implement this with FastAPI (example) or Flask.

#### FastAPI example

```python
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import JSONResponse
import numpy as np

app = FastAPI()

# For demo, pretend this is your storage
VIDEO_DATA = {}  # { video_id: np.ndarray }

def get_video_matrix(video_id: str) -> np.ndarray:
    arr = VIDEO_DATA.get(video_id)
    if arr is None:
        raise HTTPException(status_code=404, detail="Video data not found")
    return arr

@app.get("/video/{video_id}/heatmap/meta")
def get_heatmap_meta(video_id: str):
    values = get_video_matrix(video_id)
    frame_count, point_count = values.shape
    return {
        "width": frame_count,
        "height": point_count,
        "dtype": "float32",  # we know what we use
        "min": float(values.min()),
        "max": float(values.max()),
    }

@app.get("/video/{video_id}/heatmap/raw")
def get_heatmap_raw(video_id: str):
    values = get_video_matrix(video_id)
    # Ensure float32 and contiguous
    values = np.asarray(values, dtype=np.float32, order="C")

    # Return raw bytes
    return Response(
        content=values.tobytes(),
        media_type="application/octet-stream",
        headers={
            "X-Width": str(values.shape[0]),
            "X-Height": str(values.shape[1]),
            "X-Dtype": "float32",
        },
    )
```

You can also gzip-compress at the HTTP server level (nginx, uvicorn, etc.).

---

## 3. Vue frontend with Canvas

Key steps:

1. Fetch meta JSON (width, height, min, max).
2. Fetch raw data as `ArrayBuffer`.
3. Wrap it in a `Float32Array`.
4. Convert values → colors and write to `ImageData`.
5. Draw onto a canvas; for zoom/pan, transform when drawing.

I’ll write a simple Vue 3 SFC-style example.

### 3.1 Template

```vue
<template>
  <div
    ref="container"
    class="heatmap-container"
    @wheel.prevent="onWheel"
    @mousedown.prevent="onMouseDown"
  >
    <canvas ref="canvas"></canvas>
    <div v-if="hoverInfo" class="tooltip" :style="tooltipStyle">
      frame: {{ hoverInfo.frame }}<br />
      index: {{ hoverInfo.index }}<br />
      value: {{ hoverInfo.value.toFixed(3) }}
    </div>
  </div>
</template>
```

You’d style `.heatmap-container` as `position: relative` and `.tooltip` as `position: absolute`.

### 3.2 Script (logic)

```vue
<script setup lang="ts">
import { ref, onMounted, watch, computed } from "vue";

interface HeatmapMeta {
  width: number;   // frames
  height: number;  // indices
  dtype: string;
  min: number;
  max: number;
}

const props = defineProps<{
  videoId: string;
}>();

const canvas = ref<HTMLCanvasElement | null>(null);
const container = ref<HTMLDivElement | null>(null);

const meta = ref<HeatmapMeta | null>(null);
const data = ref<Float32Array | null>(null);  // flattened [frame0 idx0..idxN, frame1 ...]

// View transform
const scale = ref(4);  // visual zoom factor (pixels per data cell)
const offsetX = ref(0);
const offsetY = ref(0);

// Hover info
const hoverInfo = ref<{ frame: number; index: number; value: number } | null>(null);
const mousePos = ref<{ x: number; y: number } | null>(null);

const tooltipStyle = computed(() => {
  if (!mousePos.value) return {};
  return {
    left: mousePos.value.x + 10 + "px",
    top: mousePos.value.y + 10 + "px",
  };
});

onMounted(async () => {
  await loadData();
  renderHeatmap();
  setupMouseMove();
});

watch([meta, data, scale, offsetX, offsetY], () => {
  renderHeatmap();
});

async function loadData() {
  // 1. Fetch meta
  const metaResp = await fetch(`/video/${props.videoId}/heatmap/meta`);
  const metaJson = await metaResp.json();
  meta.value = metaJson;

  // 2. Fetch raw data
  const rawResp = await fetch(`/video/${props.videoId}/heatmap/raw`);
  const buffer = await rawResp.arrayBuffer();

  // We know it's float32
  data.value = new Float32Array(buffer);
}

/**
 * Precompute a simple color map: value in [0, 1] → RGB
 * Example: blue → green → red
 */
function createColormap(): Uint8Array {
  const map = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255; // 0..1
    // Simple gradient: blue (0) → green (0.5) → red (1)
    let r = 0, g = 0, b = 0;
    if (t < 0.5) {
      // blue → green
      const k = t / 0.5; // 0..1
      r = 0;
      g = Math.round(255 * k);
      b = Math.round(255 * (1 - k));
    } else {
      // green → red
      const k = (t - 0.5) / 0.5;
      r = Math.round(255 * k);
      g = Math.round(255 * (1 - k));
      b = 0;
    }
    map[i * 3 + 0] = r;
    map[i * 3 + 1] = g;
    map[i * 3 + 2] = b;
  }
  return map;
}

const colormap = createColormap();

function renderHeatmap() {
  if (!canvas.value || !meta.value || !data.value) return;

  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;

  const { width, height, min, max } = meta.value;
  const values = data.value;

  // We create an offscreen canvas at data resolution
  const offCanvas = document.createElement("canvas");
  offCanvas.width = width;
  offCanvas.height = height;

  const offCtx = offCanvas.getContext("2d");
  if (!offCtx) return;

  const imageData = offCtx.createImageData(width, height);
  const pixels = imageData.data; // Uint8ClampedArray

  const valueRange = max - min || 1;

  // Note: We'll treat x = frame, y = index
  // Flatten index = y + x*height (because values are [frame][index])
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      const dataIndex = x * height + y;
      const v = values[dataIndex];

      // Normalize to 0..255
      let t = (v - min) / valueRange;
      if (t < 0) t = 0;
      if (t > 1) t = 1;
      const ci = Math.floor(t * 255);

      const r = colormap[ci * 3 + 0];
      const g = colormap[ci * 3 + 1];
      const b = colormap[ci * 3 + 2];

      const pixelIndex = (y * width + x) * 4;
      pixels[pixelIndex + 0] = r;
      pixels[pixelIndex + 1] = g;
      pixels[pixelIndex + 2] = b;
      pixels[pixelIndex + 3] = 255;
    }
  }

  offCtx.putImageData(imageData, 0, 0);

  // Now draw the offscreen canvas into visible canvas with zoom/pan
  const visibleWidth = width * scale.value;
  const visibleHeight = height * scale.value;

  // Resize visible canvas to container size or image size
  if (container.value) {
    canvas.value.width = container.value.clientWidth;
    canvas.value.height = container.value.clientHeight;
  } else {
    canvas.value.width = visibleWidth;
    canvas.value.height = visibleHeight;
  }

  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height);

  ctx.save();
  ctx.translate(offsetX.value, offsetY.value);
  ctx.imageSmoothingEnabled = false; // keep pixel crispness
  ctx.drawImage(offCanvas, 0, 0, visibleWidth, visibleHeight);
  ctx.restore();
}

/** Zoom with mouse wheel */
function onWheel(e: WheelEvent) {
  const delta = -e.deltaY;
  const zoomFactor = delta > 0 ? 1.1 : 0.9;
  scale.value *= zoomFactor;
}

/** Pan with mouse drag */
let isDragging = false;
let lastX = 0;
let lastY = 0;

function onMouseDown(e: MouseEvent) {
  isDragging = true;
  lastX = e.clientX;
  lastY = e.clientY;

  window.addEventListener("mousemove", onMouseMoveDrag);
  window.addEventListener("mouseup", onMouseUp);
}

function onMouseMoveDrag(e: MouseEvent) {
  if (!isDragging) return;
  const dx = e.clientX - lastX;
  const dy = e.clientY - lastY;
  lastX = e.clientX;
  lastY = e.clientY;

  offsetX.value += dx;
  offsetY.value += dy;
}

function onMouseUp() {
  isDragging = false;
  window.removeEventListener("mousemove", onMouseMoveDrag);
  window.removeEventListener("mouseup", onMouseUp);
}

/** Hover logic (convert mouse position to frame/index) */
function setupMouseMove() {
  if (!canvas.value) return;
  canvas.value.addEventListener("mousemove", (e: MouseEvent) => {
    if (!canvas.value || !meta.value || !data.value || isDragging) {
      hoverInfo.value = null;
      return;
    }

    const rect = canvas.value.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    mousePos.value = { x: mouseX, y: mouseY };

    // Undo the transform to get into data-space
    const xInImage = (mouseX - offsetX.value) / scale.value;
    const yInImage = (mouseY - offsetY.value) / scale.value;

    const frame = Math.floor(xInImage);
    const index = Math.floor(yInImage);

    if (
      frame < 0 ||
      index < 0 ||
      !meta.value ||
      frame >= meta.value.width ||
      index >= meta.value.height
    ) {
      hoverInfo.value = null;
      return;
    }

    const dataIndex = frame * meta.value.height + index;
    const value = data.value[dataIndex];

    hoverInfo.value = { frame, index, value };
  });
}
</script>
```

---

## 4. Performance & robustness tips

### Backend

* Keep values as `float32` (or even `uint16` if you can quantize).
* Enable gzip in your web server; binary compresses well.
* Optionally add:

  * `GET /video/<id>/heatmap/segment?start=&end=` to send only a subset of frames for huge datasets.
  * A cached/precomputed quantized version for “fast preview”.

### Frontend

* Avoid re-building the `ImageData` on every minor zoom/pan:

  * Build once into an offscreen canvas at native resolution.
  * For interactions, only scale/translate the offscreen canvas.
* Only recompute colors if:

  * Values change, or
  * User changes the color scale (min/max).
* Turn off `imageSmoothingEnabled` for crisp blocks.

---

### TL;DR Architectural summary

* **Python/OpenCV**:

  * Compute a `(frame_count, point_count)` NumPy array per video.
  * Expose `/meta` (JSON) + `/raw` (binary) endpoints.

* **Vue + Canvas**:

  * Load meta → load raw into `Float32Array`.
  * Generate `ImageData` once using a colormap.
  * Draw via canvas; handle zoom/pan via scale/translate.
  * Use mouse position + transform to show tooltips with exact values.

