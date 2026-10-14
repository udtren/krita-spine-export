# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Load the Qt 6 binding used by Krita 6 instead of falling through to an
  unavailable PySide6 import. Krita 5 remains supported through PyQt5.
- Include enabled Krita layer styles in exported layer and `[merge]` group PNGs,
  and use the styled projection bounds for Spine attachment geometry.
- Remove the unused vertical gap between skin preview thumbnails and their
  information labels.
- Export PNGs of non-8-bit documents (such as 32-bit float) without reporting
  "Could not write PNG": `Node.save()` returns `None` in Krita's Python API, so
  only a missing file counts as a failure. These layer exports no longer show
  the PNG options dialog for every image.
- Write layers of RGBA 16-bit integer, 16-bit float and 32-bit float documents
  with an sRGB profile directly as 8-bit PNGs, as for 8-bit documents, instead
  of through `Node.save()`. This is much faster and avoids an intermittent
  crash in Solstice with the GPU engine. Other profiles still use
  `Node.save()`.

### Added
- **show preview thumbnail** action under Tools > Scripts, opening a grid window
  of thumbnails for every group layer whose name starts with one of the
  configured prefixes (`[skin` by default).
- Skin preview groups containing a `[slot: ...head]` group with multiple image
  children now produce a separate thumbnail for each head image.
- **show spine export settings** action under Tools > Scripts, with a **Layer
  Prefixes** tab for editing the list of matched name prefixes (add, remove,
  reorder) and a **Display** tab for the preview grid column count, thumbnail
  size, and the preview window's initial width and height.
- Preview settings are persisted to `krita/spine_export/preview.json`, resolved
  relative to the installed plugin folder.

## [1.0.1] - 2026-07-18

### Changed
- Added an **Ignore hidden layers** export option, defaulting off, that skips
  hidden groups, hidden layers, and children of hidden groups when enabled.
- Layers named `_root_` anywhere in the document are now treated as non-exported
  origin markers. Their visible center becomes Spine `0,0` for exported
  attachment and bone positions.
- Split exporter internals into `models.py`, `tags.py`, and `image_writer.py`
  while keeping the existing exporter API available.
- Exported image and attachment names now include the immediate parent group
  name as a prefix, for example `front_head.png`.
- Export now processes layers from the document root instead of the active group
  layer. Root-level groups and layers whose names start with `_` are skipped.
- The export folder and Spine JSON are named after the Krita file name
  (`kritaFileName/kritaFileName.json`).

## [1.0.0] - 2026-07-17

### Added
- Group-based export workflow: the active group layer defines the export name as
  `parentGroupName_activeGroupName` (layer tags stripped), falling back to just
  the active group name when it has no group parent.
- Export dialog now asks only for an **export folder**. The plugin automatically
  creates a `<combined name>` subfolder containing `<combined name>.json` and an
  `images` folder.

### Changed
- Hidden layers, and layers inside hidden groups, are now always ignored during
  export. Only visible layers are checked and exported.

### Removed
- Removed the "Ignore hidden layers" option and checkbox; hidden-layer filtering
  is now always on.

### Fixed
- Export is cancelled with a clear message when the active node is not a group
  layer, prompting the user to change the active node.
