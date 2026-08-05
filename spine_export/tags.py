import re

from .models import LayerInfo, SpineExportError

_TAG_RE = re.compile(r"\[([^\]:]+)(?::([^\]]*))?\]")
_VALID_GROUP_TAGS = {
    "bone",
    "skin",
    "folder",
    "ignore",
    "merge",
    "name",
    "scale",
    "slot",
    "trim",
}
_VALID_LAYER_TAGS = {
    "bone",
    "skin",
    "folder",
    "ignore",
    "mesh",
    "path",
    "scale",
    "slot",
    "trim",
}


def clean_node_name(name):
    return strip_tags(name)


def tags(name: str):
    return [
        (m.group(1).lower(), (m.group(2) or "").strip())
        for m in _TAG_RE.finditer(name or "")
    ]


def has_tag(node, tag: str):
    return any(key == tag for key, _ in tags(node.name()))


def tag_value(
    node,
    tag: str,
    include_parents: list[object] | None = None,
    allow_empty: bool = False,
):
    nodes = list(include_parents or []) + [node]
    for current in reversed(nodes):
        is_group = current.type() == "grouplayer"
        valid = _VALID_GROUP_TAGS if is_group else _VALID_LAYER_TAGS
        for key, value in tags(current.name()):
            if key == tag and key in valid:
                if value:
                    return value
                if allow_empty:
                    return ""
                return strip_tags(current.name())
    return None


def float_tag(layer: LayerInfo, tag: str, default: float, path: str):
    value = tag_value(layer.node, tag, include_parents=layer.parent_chain)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise SpineExportError(f"Invalid [{tag}:{value}] on {path}")


def strip_tags(name: str):
    return _TAG_RE.sub("", name or "").strip()


def apply_name_patterns(name: str, parents: list[object]):
    result = name
    for parent in parents:
        pattern = tag_value(parent, "name", allow_empty=False)
        if pattern:
            if "*" not in pattern:
                raise SpineExportError(
                    f"[name:pattern] must contain '*': {parent.name()}"
                )
            result = pattern.replace("*", result)
    return result


def parent_prefixed_name(name: str, parents: list[object]):
    if name.startswith("/") or not parents:
        return name
    parent_name = strip_tags(parents[-1].name())
    if not parent_name:
        return name
    return parent_name + "_" + name


def folder_path(nodes: list[object]):
    parts = []
    for node in nodes:
        folder = direct_tag_value(node, "folder")
        skin = direct_tag_value(node, "skin")
        value = folder if folder is not None else skin
        if not value or value == "default":
            continue
        if value.startswith("/"):
            parts = [value.strip("/")]
        else:
            parts.append(value.strip("/"))
    return "/".join(part for part in parts if part) + ("/" if parts else "")


def skin_name(nodes: list[object]):
    skin = "default"
    for node in nodes:
        value = direct_tag_value(node, "skin")
        if value:
            skin = value.strip("/") or strip_tags(node.name())
    return skin or "default"


def bone_name(nodes: list[object]):
    bone = "root"
    for node in nodes:
        value = direct_tag_value(node, "bone")
        if value is not None:
            bone = value or strip_tags(node.name())
    return bone or "root"


def parent_bone_name(parents: list[object]):
    if not parents:
        return "root"
    return bone_name(parents[:-1])


def direct_tag_value(node, tag: str):
    for key, value in tags(node.name()):
        if key == tag:
            return value or strip_tags(node.name())
    return None


def layer_path(layer: LayerInfo):
    names = [parent.name() for parent in layer.parent_chain] + [layer.name]
    return "/".join(names)
