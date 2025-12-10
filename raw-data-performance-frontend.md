Short answer: **yes, it’s *possible*** on many machines — but **naively storing this in Vue reactive state will almost certainly murder performance and can blow up memory**. You need to be careful about:

* **How** you represent the data (plain JS objects vs typed arrays vs compressed)
* **Where** you store it (reactive vs non-reactive)
* **What you actually keep in memory at once** (all frames vs a sliding window / cache)

Let’s unpack it with numbers and then some concrete strategies.

---

## 1. Rough memory estimate

Per frame you have something like:

* `pt`: ~334 `[x,y]` pairs
* `pb`: ~334 pairs
* `pc`: ~334 pairs
* `mpp`: ~30 entries of 7 numbers each

So ~1000+ points + some extra = **≈ 2,200 numbers per frame**.

For **15,000 frames**:

```text
≈ 2,200 numbers/frame * 15,000 frames = 33,000,000+ numbers
```

In JS, a `Number` is an 8-byte float (ignoring overhead):

```text
33M numbers * 8 bytes ≈ 264,000,000 bytes ≈ 250 MB
```

That’s just the raw numeric data. In reality:

* Arrays + objects + Vue’s reactivity wrappers add a **big factor on top**.
* It’s not crazy to end up in the **500MB–1GB territory** if you store it as nested objects in reactive state.

Modern desktop browsers *can* handle that, but:

* Lower-end devices might struggle or crash.
* GC pauses and reactivity overhead can freeze your UI.

So: **storing it all as deeply reactive nested objects is a bad idea**. Storing it more compactly and non-reactively is usually fine.

---

## 2. Golden rule: keep Vue reactivity away from the raw bulk data

You almost never need reactivity on all 15,000 frames. Typically, you care about:

* Current frame
* Maybe a small neighborhood of frames
* Some derived metrics / aggregates

So do this:

### 2.1 Store the bulk data as *non-reactive*

```js
// bigData.js
import { markRaw } from 'vue';

// This could be loaded from a JSON, binary file, or generated.
const rawFrames = /* huge array of frames */;

export const frames = markRaw(rawFrames); // Vue won’t wrap every object
```

Then in your component:

```js
import { ref, computed } from 'vue';
import { frames } from './bigData';

const currentFrameIndex = ref(0);

const currentFrame = computed(() => frames[currentFrameIndex.value]);
```

* Vue only tracks `currentFrameIndex`.
* It does **not** create proxies and watchers on all those nested arrays.
* Access is still fast; you just lose automatic reactivity on the internals, which you don’t need anyway.

If you’re fetching data:

```js
const frames = markRaw(JSON.parse(responseText));
```

Or if using a store (Pinia), you can do:

```js
state: () => ({
  frames: markRaw([]) // later assign the huge dataset
})
```

---

## 3. Use more compact structures (TypedArrays)

Right now every `[x, y]` is:

* An array instance
* Two `Number`s
* Referenced in another array

That’s a *lot* of objects.

Better: flatten into typed arrays.

Example for one array like `pt`:

```js
// Flatten: [x0, y0, x1, y1, x2, y2, ...]
const ptCoords = new Int16Array(numFrames * pointsPerFrame * 2);

// ptCoords[frameIndex * pointsPerFrame * 2 + pointIndex * 2 + 0] = x
// ptCoords[frameIndex * pointsPerFrame * 2 + pointIndex * 2 + 1] = y
```

Across `pt`, `pb`, `pc`, `mpp`, you can:

* Use `Float32Array` or `Int16Array` depending on your ranges
* Store as **one big `ArrayBuffer`** for each “channel”

Benefits:

* Much less overhead than millions of little arrays/objects
* **More predictable memory usage**
* Much faster for drawing to Canvas/WebGL

Still mark them as non-reactive:

```js
import { markRaw } from 'vue';

export const dataBuffer = markRaw({
  pt: new Int16Array(...),
  pb: new Int16Array(...),
  pc: new Int16Array(...),
  mpp: new Float32Array(...),
});
```

---

## 4. Avoid big synchronous work on the main thread

Even if memory is OK, just *loading* and parsing a 500MB JSON in one go will:

* Block the main thread for a while
* Make the Vue UI feel frozen

Strategies:

1. **Chunk parsing / progressive loading**

   * Split data file on the server
   * Load, say, 500 frames at a time

2. **Web Worker for parsing / preprocessing**

   * Fetch raw file in a worker
   * Parse JSON or binary
   * Send back typed array buffers via `postMessage` (transferable objects, zero-copy)
   * Main thread stays responsive

3. **Use binary format instead of JSON**

   * JSON is huge, slow to parse
   * A simple custom binary format or something like protobuf/flatbuffers is much smaller and faster

---

## 5. What I’d do in your situation

If I were implementing this in Vue:

1. **Preprocess on the backend** into a compact binary format.
2. **Load into Web Worker**, parse to `ArrayBuffer`s and `Float32Array` / `Int16Array`.
3. **Transfer buffers to main thread** and wrap them in a `markRaw` object.
4. Have Vue only track:

   * `currentFrameIndex`
   * A few settings (zoom, colors, etc.)
5. Draw with **Canvas** or **WebGL** in a component that reads from these buffers.

This will let you keep *all* 15,000 frames in memory on most desktop systems without the frontend becoming unresponsive — and without flirting too dangerously with memory limits.