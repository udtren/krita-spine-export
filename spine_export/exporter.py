import json
import os

try:
    from PyQt6.QtCore import QRect
except ImportError:
    from PyQt5.QtCore import QRect

from .image_writer import write_layer_png, write_template_png
from .models import (
    BoneInfo,
    ExportResult,
    ExportSettings,
    LayerInfo,
    SlotInfo,
    SpineExportError,
)
from .tags import (
    apply_name_patterns,
    bone_name,
    clean_node_name,
    float_tag,
    folder_path,
    has_tag,
    layer_path,
    parent_bone_name,
    parent_prefixed_name,
    skin_name,
    strip_tags,
    tag_value,
)

_BLEND_MAP = {
    "multiply": "multiply",
    "screen": "screen",
    "add": "additive",
    "linear dodge": "additive",
    "linear_dodge": "additive",
    "linearDodge": "additive",
}


def document_export_name(document):
    filename = document.fileName() or ""
    if not filename:
        raise SpineExportError("Save the Krita document before exporting to Spine.")
    name = clean_node_name(os.path.splitext(os.path.basename(filename))[0])
    if not name:
        raise SpineExportError(
            "The Krita document file name is not a valid export name."
        )
    return name, name


def active_group_export_name(document):
    return document_export_name(document)


class SpineExporter:
    def __init__(self, document, settings: ExportSettings):
        self.document = document
        self.settings = settings
        self.layers: list[LayerInfo] = []
        self.root_marker: LayerInfo | None = None
        self.root_origin: tuple[float, float] = (0.0, 0.0)
        self.bones: dict[str, BoneInfo] = {"root": BoneInfo("root")}
        self.slots: dict[str, SlotInfo] = {}
        self.skin_order: list[str] = []
        self.errors: list[str] = []

    def export(self) -> ExportResult:
        if (
            not self.settings.write_json
            and not self.settings.write_images
            and not self.settings.write_template
        ):
            raise SpineExportError("Enable at least one output option.")
        if self.settings.write_json and not self.settings.json_path:
            raise SpineExportError("Choose a Spine JSON path.")
        if self.settings.write_images and not self.settings.images_dir:
            raise SpineExportError("Choose an images output folder.")

        document_export_name(self.document)

        self.document.waitForDone()
        self.document.refreshProjection()

        self._collect_root_marker()
        self._collect_layers()
        self._set_root_origin()
        if not self.layers:
            raise SpineExportError("No exportable layers found.")

        self._prepare_layers()

        if self.settings.write_images:
            os.makedirs(self.settings.images_dir, exist_ok=True)
            for layer in self.layers:
                write_layer_png(self.document, self.settings, layer)

        if self.settings.write_template:
            write_template_png(self.document, self.settings)

        if self.settings.write_json:
            os.makedirs(
                os.path.dirname(os.path.abspath(self.settings.json_path)), exist_ok=True
            )
            with open(
                self.settings.json_path, "w", encoding="utf-8", newline="\n"
            ) as fh:
                json.dump(self._build_json(), fh, ensure_ascii=False, indent=2)
                fh.write("\n")

        return ExportResult(
            attachment_count=len(self.layers),
            json_path=self.settings.json_path if self.settings.write_json else None,
            images_dir=self.settings.images_dir if self.settings.write_images else None,
        )

    def _collect_root_marker(self):
        root = self.document.rootNode()
        if root is None:
            return
        for node in root.childNodes():
            self._walk_root_marker(node, [])

    def _walk_root_marker(self, node, parents: list[object]):
        if self._should_ignore_hidden(node):
            return
        name = node.name()
        node_type = node.type()
        if node_type != "grouplayer" and strip_tags(name) == "_root_":
            self._set_root_marker(node, parents, name)
            return
        if node_type == "grouplayer":
            for child in node.childNodes():
                self._walk_root_marker(child, parents + [node])

    def _collect_layers(self):
        root = self.document.rootNode()
        if root is None:
            raise SpineExportError("The Krita document has no root node.")
        for node in root.childNodes():
            if self._is_ignored_root_node(node):
                continue
            self._walk_node(node, [])

    def _is_ignored_root_node(self, node):
        return (node.name() or "").startswith("_")

    def _should_ignore_hidden(self, node):
        return self.settings.ignore_hidden_layers and not node.visible()

    def _walk_node(self, node, parents: list[object]):
        name = node.name()
        node_type = node.type()
        if self._should_ignore_hidden(node):
            return
        if has_tag(node, "ignore"):
            return
        if node_type in (
            "transparencymask",
            "filtermask",
            "transformmask",
            "selectionmask",
            "colorizemask",
        ):
            return
        if has_tag(node, "overlay"):
            return
        if node_type != "grouplayer" and strip_tags(name) == "_root_":
            return

        is_group = node_type == "grouplayer"
        if is_group and has_tag(node, "merge"):
            if self._has_exportable_projection(node):
                self.layers.append(
                    LayerInfo(
                        node=node,
                        parent_chain=list(parents),
                        name=name,
                        clean_name=strip_tags(name),
                        visible=node.visible(),
                    )
                )
            return
        if is_group:
            for child in node.childNodes():
                self._walk_node(child, parents + [node])
            return

        if self._has_exportable_projection(node):
            self.layers.append(
                LayerInfo(
                    node=node,
                    parent_chain=list(parents),
                    name=name,
                    clean_name=strip_tags(name),
                    visible=node.visible(),
                )
            )

    def _set_root_marker(self, node, parents: list[object], name: str):
        if self.root_marker is not None:
            raise SpineExportError(
                "Multiple _root_ marker layers found: {0} and {1}".format(
                    layer_path(self.root_marker),
                    "/".join([parent.name() for parent in parents] + [name]),
                )
            )
        self.root_marker = LayerInfo(
            node=node,
            parent_chain=list(parents),
            name=name,
            clean_name=strip_tags(name),
            visible=node.visible(),
        )

    def _set_root_origin(self):
        if self.root_marker is None:
            return
        rect = self.root_marker.node.bounds()
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            raise SpineExportError(
                f"Root marker layer has no visible pixels: {layer_path(self.root_marker)}"
            )
        center_x = rect.x() + rect.width() / 2.0
        center_y = rect.y() + rect.height() / 2.0
        self.root_origin = (
            center_x * self.settings.scale,
            (self.document.height() - center_y) * self.settings.scale,
        )

    def _apply_root_origin(self, x: float, y: float):
        origin_x, origin_y = self.root_origin
        return x - origin_x, y - origin_y

    def _prepare_layers(self):
        for layer in self.layers:
            clean = apply_name_patterns(
                layer.clean_name or layer.name, layer.parent_chain
            )
            clean = clean[:-4] if clean.lower().endswith(".png") else clean
            if not clean:
                raise SpineExportError(
                    f"Layer name is empty after removing tags: {layer_path(layer)}"
                )

            export_name = parent_prefixed_name(clean, layer.parent_chain)
            folders = folder_path(layer.parent_chain + [layer.node])
            path_tag = tag_value(layer.node, "path", include_parents=layer.parent_chain)
            layer.attachment_name = (
                export_name if export_name.startswith("/") else folders + export_name
            )
            layer.attachment_name = layer.attachment_name.lstrip("/")
            if path_tag:
                layer.attachment_path = (
                    path_tag[1:] if path_tag.startswith("/") else folders + path_tag
                )
            else:
                layer.attachment_path = layer.attachment_name
            layer.attachment_path = (
                layer.attachment_path[:-4]
                if layer.attachment_path.lower().endswith(".png")
                else layer.attachment_path
            )

            layer.skin_name = skin_name(layer.parent_chain + [layer.node])
            if layer.skin_name != "default" and layer.attachment_name.startswith(
                layer.skin_name + "/"
            ):
                layer.placeholder_name = layer.attachment_name[
                    len(layer.skin_name) + 1 :
                ]
            else:
                layer.placeholder_name = layer.attachment_name
            layer.slot_name = tag_value(
                layer.node, "slot", include_parents=layer.parent_chain
            ) or export_name.lstrip("/")
            layer.bone_name = bone_name(layer.parent_chain + [layer.node])
            layer.scale = float_tag(layer, "scale", 1.0, layer_path(layer))
            layer.mesh = tag_value(
                layer.node, "mesh", include_parents=layer.parent_chain, allow_empty=True
            )
            layer.blend = self._blend(layer.node)
            layer.rect = self._export_rect(layer)

            if (
                layer.rect is None
                or layer.rect.width() <= 0
                or layer.rect.height() <= 0
            ):
                raise SpineExportError(
                    f"Layer has no visible pixels: {layer_path(layer)}"
                )

            w = layer.rect.width() + self.settings.padding * 2
            h = layer.rect.height() + self.settings.padding * 2
            layer.exported_size = (
                max(1, int(round(w * self.settings.scale))),
                max(1, int(round(h * self.settings.scale))),
            )
            center_x = layer.rect.x() + layer.rect.width() / 2.0
            center_y = layer.rect.y() + layer.rect.height() / 2.0
            x = center_x * self.settings.scale
            y = (self.document.height() - center_y) * self.settings.scale
            layer.spine_xy = self._apply_root_origin(x, y)
            self._register_bone(layer)
            self._register_slot(layer)
            if layer.skin_name not in self.skin_order:
                self.skin_order.append(layer.skin_name)

        self._check_duplicates()

    def _register_bone(self, layer: LayerInfo):
        if layer.bone_name == "root":
            return
        parent_bone = parent_bone_name(layer.parent_chain)
        bone = self.bones.get(layer.bone_name)
        if bone is None:
            bone = BoneInfo(
                layer.bone_name, None if parent_bone == "root" else parent_bone
            )
            self.bones[layer.bone_name] = bone
        rect = layer.rect
        if rect is not None and not bone.has_position:
            x = (rect.x() + rect.width() / 2.0) * self.settings.scale
            y = (
                self.document.height() - (rect.y() + rect.height() / 2.0)
            ) * self.settings.scale
            bone.x, bone.y = self._apply_root_origin(x, y)
            bone.has_position = True

    def _register_slot(self, layer: LayerInfo):
        slot = self.slots.get(layer.slot_name)
        if slot is None:
            slot = SlotInfo(layer.slot_name, layer.bone_name)
            self.slots[layer.slot_name] = slot
        if slot.attachment is None and layer.visible:
            slot.attachment = layer.placeholder_name
        if not slot.blend and layer.blend:
            slot.blend = layer.blend
        slot.layers.append(layer)

    def _check_duplicates(self):
        seen = set()
        for layer in self.layers:
            key = (layer.skin_name, layer.slot_name, layer.placeholder_name)
            if key in seen:
                raise SpineExportError(
                    f"Duplicate attachment placeholder '{layer.placeholder_name}' in skin '{layer.skin_name}', slot '{layer.slot_name}'."
                )
            seen.add(key)

    def _build_json(self):
        data = {
            "skeleton": {"images": self._json_images_path()},
            "KritaToSpine": {
                "scale": self.settings.scale,
                "padding": self.settings.padding,
                "trim": self.settings.trim_whitespace,
            },
            "bones": self._json_bones(),
            "slots": self._json_slots(),
            "animations": {"animation": {}},
        }
        skins = self._json_skins()
        if skins:
            data["skins"] = skins
        return data

    def _json_bones(self):
        bones = [{"name": "root"}]
        for name, bone in self.bones.items():
            if name == "root":
                continue
            item = {"name": name}
            if bone.parent:
                item["parent"] = bone.parent
            if bone.has_position:
                item["x"] = round(bone.x, 4)
                item["y"] = round(bone.y, 4)
            bones.append(item)
        return bones

    def _json_slots(self):
        slots = []
        for slot in self.slots.values():
            item = {"name": slot.name, "bone": slot.bone or "root"}
            if slot.attachment:
                item["attachment"] = slot.attachment
            if slot.blend:
                item["blend"] = slot.blend
            slots.append(item)
        return slots

    def _json_skins(self):
        if self.settings.legacy_json:
            skins = {}
            for skin in self.skin_order:
                skin_slots = {}
                for slot in self.slots.values():
                    attachments = self._attachments_for_slot(slot, skin)
                    if attachments:
                        skin_slots[slot.name] = attachments
                if skin_slots:
                    skins[skin] = skin_slots
            return skins

        skins = []
        for skin in self.skin_order:
            attachments_by_slot = {}
            for slot in self.slots.values():
                attachments = self._attachments_for_slot(slot, skin)
                if attachments:
                    attachments_by_slot[slot.name] = attachments
            if attachments_by_slot:
                skins.append({"name": skin, "attachments": attachments_by_slot})
        return skins

    def _attachments_for_slot(self, slot: SlotInfo, skin: str):
        attachments = {}
        for layer in slot.layers:
            if layer.skin_name != skin:
                continue
            attachment = self._attachment_json(layer)
            attachments[layer.placeholder_name] = attachment
        return attachments

    def _attachment_json(self, layer: LayerInfo):
        x, y = layer.spine_xy
        width, height = layer.exported_size
        data = {
            "x": round(x, 4),
            "y": round(y, 4),
            "width": width,
            "height": height,
        }
        if layer.attachment_name != layer.placeholder_name:
            data["name"] = layer.attachment_name
        if layer.attachment_path != layer.attachment_name:
            data["path"] = layer.attachment_path
        if layer.scale != 1:
            data["scaleX"] = round(1 / layer.scale, 6)
            data["scaleY"] = round(1 / layer.scale, 6)
        if layer.mesh is not None:
            if layer.mesh:
                data.update({"type": "linkedmesh", "parent": layer.mesh})
                if layer.skin_name != "default":
                    data["skin"] = layer.skin_name
            else:
                data.update(
                    {
                        "type": "mesh",
                        "vertices": [
                            width / 2,
                            -height / 2,
                            -width / 2,
                            -height / 2,
                            -width / 2,
                            height / 2,
                            width / 2,
                            height / 2,
                        ],
                        "uvs": [1, 1, 0, 1, 0, 0, 1, 0],
                        "triangles": [1, 2, 3, 1, 3, 0],
                        "hull": 4,
                    }
                )
        return data

    def _export_rect(self, layer: LayerInfo):
        trim_value = tag_value(
            layer.node, "trim", include_parents=layer.parent_chain, allow_empty=True
        )
        trim = (
            self.settings.trim_whitespace
            if trim_value is None
            else trim_value.lower() != "false"
        )
        if trim:
            return layer.node.bounds()
        return QRect(0, 0, self.document.width(), self.document.height())

    def _has_exportable_projection(self, node):
        try:
            bounds = node.bounds()
            return bounds is not None and bounds.width() > 0 and bounds.height() > 0
        except Exception:
            return False

    def _blend(self, node):
        try:
            mode = node.blendingMode()
        except Exception:
            return None
        return _BLEND_MAP.get(mode, _BLEND_MAP.get(str(mode).lower()))

    def _json_images_path(self):
        if not self.settings.images_dir:
            return ""
        if self.settings.json_path:
            try:
                rel = os.path.relpath(
                    self.settings.images_dir, os.path.dirname(self.settings.json_path)
                )
                return rel.replace(os.sep, "/") + "/"
            except ValueError:
                pass
        return self.settings.images_dir.replace(os.sep, "/") + "/"
