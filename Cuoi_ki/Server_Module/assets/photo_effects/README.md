# Photo effect assets

For a captured photo set, the Server applies each slot's selected color filter
and face overlay to a rendered copy of the high-resolution original. The raw
originals remain unchanged and the live camera preview is not modified. Overlay
and frame assets are loaded when the Server starts, so restart it after adding
or changing them.

## Folders

- `filters/`: reserved for custom color-filter assets such as `.cube` LUT files.
  The existing built-in filters are currently implemented in
  `server/image_processing.py`.
- `face_overlays/<overlay_id>/`: one folder per face sticker. Put a transparent
  RGBA PNG named `overlay.png` and a `metadata.json` in each folder.
- `frames/`: PNG photo-frame templates. The root `manifest.json` lists each
  template's canvas dimensions, four photo-slot rectangles, and reserved QR
  rectangle. Admin lets users choose a template, place four selected originals
  into its slots, and preview the transparent frame composited over them.

The supplied `manifest.json` also lists the built-in color filters and face
overlays. Filter entries reference filters already implemented by the Server;
they are not external LUT files.

Example:

```text
photo_effects/
├── filters/
└── face_overlays/
    ├── glasses/
    │   ├── overlay.png
    │   └── metadata.json
    └── crown/
        ├── overlay.png
        └── metadata.json
```

Example `metadata.json` for a crown:

```json
{
  "id": "crown",
  "name": "Crown",
  "anchor": "forehead",
  "width_ratio": 1.15,
  "pivot": [0.5, 0.85],
  "offset": [0.0, -0.08],
  "angle_offset": 0.0
}
```

Use `"anchor": "eyes"` for glasses and `"anchor": "forehead"` for crowns or
hats. `pivot` is normalized to the PNG dimensions; `offset` is relative to the
face reference width. The Server validates the PNG and metadata at startup.

Admin supports per-slot built-in color effects and optional face overlays. It
center-crops each original to fit a slot, detects faces on the cropped image,
applies the selected color effect, and composites the sticker afterward. The
frame is layered above the processed photos. QR placement is reserved in the
manifest but QR generation and final export are not part of this milestone.

Face overlays require a MediaPipe Face Landmarker task model at
`AI/models/face_landmarker.task`. Its path, number of faces, and confidence
thresholds are configured in `Server_Module/config/config.yaml`.
