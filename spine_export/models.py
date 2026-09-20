from dataclasses import dataclass, field
from typing import List, Optional, Tuple


class SpineExportError(Exception):
    pass


@dataclass
class ExportSettings:
    json_path: str
    images_dir: str
    scale: float = 1.0
    padding: int = 1
    trim_whitespace: bool = True
    ignore_hidden_layers: bool = False
    write_json: bool = True
    write_images: bool = True
    write_template: bool = False
    legacy_json: bool = True


@dataclass
class ExportResult:
    attachment_count: int
    json_path: Optional[str]
    images_dir: Optional[str]


@dataclass
class LayerInfo:
    node: object
    parent_chain: List[object]
    name: str
    clean_name: str
    attachment_name: str = ""
    attachment_path: str = ""
    placeholder_name: str = ""
    slot_name: str = ""
    skin_name: str = "default"
    bone_name: str = "root"
    scale: float = 1.0
    mesh: Optional[str] = None
    rect: Optional[object] = None
    exported_size: Tuple[int, int] = (0, 0)
    spine_xy: Tuple[float, float] = (0.0, 0.0)
    blend: Optional[str] = None
    visible: bool = True
    rendered_image: Optional[object] = None
    rendered_rect: Optional[object] = None


@dataclass
class BoneInfo:
    name: str
    parent: Optional[str] = None
    x: float = 0.0
    y: float = 0.0
    has_position: bool = False


@dataclass
class SlotInfo:
    name: str
    bone: str = "root"
    attachment: Optional[str] = None
    blend: Optional[str] = None
    layers: List[LayerInfo] = field(default_factory=list)
