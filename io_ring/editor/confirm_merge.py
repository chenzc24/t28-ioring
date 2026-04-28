# -*- coding: utf-8 -*-
"""Pure merge/normalize helpers for IO editor confirm flow."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, List, Optional


# Maintainer-editable defaults used when editor adds new components.
# Supported families: pad / filler / corner / blank.
EDITOR_COMPONENT_TEMPLATES = {
    "pad": {
        "view_name": "layout",
        "pad_width": 20,
        "pad_height": 110,
    },
    "filler": {
        "view_name": "layout",
        "pad_width": 10,
        "pad_height": 110,
    },
    "corner": {
        "view_name": "layout",
        "pad_width": 110,
        "pad_height": 110,
    },
    "blank": {
        "view_name": "layout",
        "pad_width": 10,
        "pad_height": 110,
    },
}

# Runtime/UI-only fields that should never persist into confirmed payload.
RUNTIME_ONLY_FIELDS = {
    "meta",
    "side",
    "order",
    "position_abs",
    "position_xy",
    "x",
    "y",
    "z",
    "selected",
    "dragging",
    "hovered",
    "isSelected",
    "isDragging",
    "displayColor",
    "ui_state",
    "_relative_position",
    "_order_from_relative",
    "_original_position",
}

# Structural fields that must come from editor-confirmed semantics and must not
# be indirectly overridden by runtime noise.
PROTECTED_STRUCTURAL_FIELDS = {"position", "position_str", "type", "name", "device"}


def _is_empty_pin_payload(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict) and not value:
        return True
    return False


def _resolve_process_node(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    ring_config = payload.get("ring_config")
    if not isinstance(ring_config, dict):
        return ""
    process_node = ring_config.get("process_node")
    if not isinstance(process_node, str):
        return ""
    return process_node.strip().upper()


def _strip_t28_editor_geometry(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    normalized = deepcopy(payload)
    for key in ("instances", "layout_data"):
        items = normalized.get(key)
        if not isinstance(items, list):
            continue

        cleaned_items = []
        for item in items:
            if not isinstance(item, dict):
                cleaned_items.append(item)
                continue

            cleaned = dict(item)
            cleaned.pop("pad_width", None)
            cleaned.pop("pad_height", None)
            cleaned.pop("filler_width", None)
            cleaned.pop("filler_height", None)
            cleaned_items.append(cleaned)

        normalized[key] = cleaned_items

    return normalized


def guess_component_type(instance: dict) -> str:
    comp_type = str(instance.get("type", "")).strip().lower()
    if comp_type in EDITOR_COMPONENT_TEMPLATES:
        return comp_type

    device = str(instance.get("device", "")).upper()
    if device == "BLANK":
        return "blank"
    if device in {"PCORNER", "PCORNERA_G", "PCORNER_G"}:
        return "corner"
    if device.startswith("PFILLER") or device == "PRCUTA_G" or "RCUT" in device:
        return "filler"
    return "pad"


def infer_filler_pad_width(device: str) -> int:
    match = re.search(r"PFILLER(\d+)", (device or "").upper())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return EDITOR_COMPONENT_TEMPLATES["filler"]["pad_width"]
    return EDITOR_COMPONENT_TEMPLATES["filler"]["pad_width"]


def position_from_side_order(instance: dict, meta: dict) -> Optional[str]:
    side = instance.get("side")
    order = instance.get("order")
    if side in {"top", "right", "bottom", "left"}:
        if isinstance(order, int) and order >= 1:
            return f"{side}_{order - 1}"
        if isinstance(order, str) and order.isdigit():
            return f"{side}_{int(order) - 1}"

    if side == "corner":
        location = (meta or {}).get("location")
        if location in {"top_left", "top_right", "bottom_left", "bottom_right"}:
            return location
    return None


def normalize_editor_instance(instance: dict) -> dict:
    normalized = dict(instance)
    meta = normalized.get("meta", {}) if isinstance(normalized.get("meta"), dict) else {}

    comp_type = guess_component_type(normalized)
    template = dict(EDITOR_COMPONENT_TEMPLATES[comp_type])
    if comp_type == "filler":
        template["pad_width"] = infer_filler_pad_width(str(normalized.get("device", "")))
    if comp_type == "blank":
        pad_width = normalized.get("pad_width")
        pad_height = normalized.get("pad_height")
        if isinstance(pad_width, (int, float)) and pad_width > 0:
            template["pad_width"] = int(pad_width)
        if isinstance(pad_height, (int, float)) and pad_height > 0:
            template["pad_height"] = int(pad_height)

    for key, value in template.items():
        if normalized.get(key) in (None, ""):
            normalized[key] = value

    position = normalized.get("position")
    if not isinstance(position, str):
        rel_pos = meta.get("_relative_position")
        if isinstance(rel_pos, str) and rel_pos:
            normalized["position"] = rel_pos
        else:
            rebuilt_position = position_from_side_order(normalized, meta)
            if rebuilt_position:
                normalized["position"] = rebuilt_position

    for runtime_key in ("side", "order", "_relative_position", "_order_from_relative"):
        normalized.pop(runtime_key, None)

    for runtime_key in RUNTIME_ONLY_FIELDS:
        if runtime_key not in PROTECTED_STRUCTURAL_FIELDS:
            normalized.pop(runtime_key, None)

    normalized.pop("meta", None)
    return normalized


def normalize_editor_payload_for_confirm(data: Any) -> Any:
    if not isinstance(data, dict):
        return data

    normalized = deepcopy(data)
    for key in ("layout_data", "instances"):
        items = normalized.get(key)
        if isinstance(items, list):
            normalized[key] = [
                normalize_editor_instance(item) if isinstance(item, dict) else item
                for item in items
            ]

    return normalized


def instance_key(instance: dict) -> Optional[str]:
    if not isinstance(instance, dict):
        return None

    name = str(instance.get("name", "")).strip()
    device = str(instance.get("device", "")).strip()
    comp_type = str(instance.get("type", "")).strip()
    if name and device and comp_type:
        return f"ndt:{name}|{device}|{comp_type}"

    instance_id = instance.get("id")
    if isinstance(instance_id, str) and instance_id.strip():
        return f"id:{instance_id.strip()}"

    return None


def instance_signature(instance: dict) -> Optional[str]:
    if not isinstance(instance, dict):
        return None

    name = str(instance.get("name", "")).strip()
    device = str(instance.get("device", "")).strip()
    comp_type = str(instance.get("type", "")).strip()
    if name and device and comp_type:
        return f"ndt:{name}|{device}|{comp_type}"
    return None


def merge_key_with_duplicate_guard(
    instance: dict,
    base_sig_counts: dict,
    incoming_sig_counts: dict,
) -> Optional[str]:
    instance_id = instance.get("id")
    if isinstance(instance_id, str) and instance_id.strip():
        return f"id:{instance_id.strip()}"

    sig = instance_signature(instance)
    if sig:
        duplicate_count = max(base_sig_counts.get(sig, 0), incoming_sig_counts.get(sig, 0))
        if duplicate_count > 1:
            position = instance.get("position")
            if isinstance(position, str) and position.strip():
                return f"{sig}|pos:{position.strip()}"
        return sig
    return None


def apply_existing_shape(base_item: dict, incoming_item: dict) -> dict:
    updated = dict(base_item)
    sanitized_incoming = {
        key: value
        for key, value in incoming_item.items()
        if key not in RUNTIME_ONLY_FIELDS or key in PROTECTED_STRUCTURAL_FIELDS
    }

    # FE-first: incoming editor fields are authoritative unless explicitly empty pin payload.
    for key, value in sanitized_incoming.items():
        if key == "meta":
            continue
        if key == "pin_connection" and _is_empty_pin_payload(value):
            continue
        updated[key] = value

    for key in PROTECTED_STRUCTURAL_FIELDS:
        if key in sanitized_incoming and sanitized_incoming.get(key) not in (None, ""):
            updated[key] = sanitized_incoming[key]

    updated.pop("meta", None)
    return updated


def build_new_instance_from_template(new_item: dict, base_instances: List[dict], ring_config: dict) -> dict:
    del base_instances  # No longer used: FE-first should not be ref-driven.

    sanitized_new_item = {
        key: value
        for key, value in new_item.items()
        if key not in RUNTIME_ONLY_FIELDS or key in PROTECTED_STRUCTURAL_FIELDS
    }

    comp_type = guess_component_type(new_item)
    template = dict(EDITOR_COMPONENT_TEMPLATES[comp_type])
    if comp_type == "filler":
        template["pad_width"] = infer_filler_pad_width(str(new_item.get("device", "")))
    if comp_type == "blank":
        pad_width = new_item.get("pad_width")
        pad_height = new_item.get("pad_height")
        if isinstance(pad_width, (int, float)) and pad_width > 0:
            template["pad_width"] = int(pad_width)
        if isinstance(pad_height, (int, float)) and pad_height > 0:
            template["pad_height"] = int(pad_height)

    # FE-first: trust incoming new instance, only fill missing defaults.
    created = dict(sanitized_new_item)

    for k, v in template.items():
        if created.get(k) in (None, ""):
            created[k] = v

    if created.get("view_name") in (None, ""):
        created["view_name"] = ring_config.get("view_name", "layout")
    if created.get("pad_width") in (None, ""):
        created["pad_width"] = ring_config.get("pad_width", template.get("pad_width", 20))
    if created.get("pad_height") in (None, ""):
        created["pad_height"] = ring_config.get("pad_height", template.get("pad_height", 110))

    # Backward compatibility: downstream logic may still reference filler_* dimensions.
    process_node = str(ring_config.get("process_node", "")).strip().upper()
    if process_node != "T28" and comp_type in {"filler", "blank"}:
        if created.get("filler_width") in (None, ""):
            created["filler_width"] = created.get("pad_width")
        if created.get("filler_height") in (None, ""):
            created["filler_height"] = created.get("pad_height")

    for runtime_key in RUNTIME_ONLY_FIELDS:
        if runtime_key not in PROTECTED_STRUCTURAL_FIELDS:
            created.pop(runtime_key, None)

    created.pop("meta", None)
    return created


def merge_instances_with_structure(base_instances: List[dict], incoming_instances: List[dict], ring_config: dict) -> List[dict]:
    if not isinstance(base_instances, list):
        base_instances = []
    if not isinstance(incoming_instances, list):
        incoming_instances = []

    normalized_incoming = [
        normalize_editor_instance(item) if isinstance(item, dict) else item
        for item in incoming_instances
    ]
    normalized_incoming = [item for item in normalized_incoming if isinstance(item, dict)]

    base_sig_counts = {}
    for item in base_instances:
        sig = instance_signature(item)
        if sig:
            base_sig_counts[sig] = base_sig_counts.get(sig, 0) + 1

    incoming_sig_counts = {}
    for item in normalized_incoming:
        sig = instance_signature(item)
        if sig:
            incoming_sig_counts[sig] = incoming_sig_counts.get(sig, 0) + 1

    incoming_by_key = {}
    incoming_order = []
    for item in normalized_incoming:
        key = merge_key_with_duplicate_guard(item, base_sig_counts, incoming_sig_counts)
        if key is None:
            continue
        if key not in incoming_by_key:
            incoming_order.append(key)
        incoming_by_key[key] = item

    base_by_key = {}
    base_order = []
    for item in base_instances:
        if not isinstance(item, dict):
            continue
        key = merge_key_with_duplicate_guard(item, base_sig_counts, incoming_sig_counts)
        if key is None:
            continue
        if key not in base_by_key:
            base_order.append(key)
        base_by_key[key] = item

    merged_items = {}

    for key in base_order:
        if key in incoming_by_key:
            merged_items[key] = apply_existing_shape(base_by_key[key], incoming_by_key[key])

    for key in incoming_order:
        if key not in merged_items:
            incoming_item = incoming_by_key[key]
            merged_items[key] = build_new_instance_from_template(incoming_item, base_instances, ring_config)

    merged_order = [k for k in base_order if k in merged_items] + [k for k in incoming_order if k not in base_order]
    return [merged_items[k] for k in merged_order]


def build_confirmed_payload(source_payload: dict, editor_payload: dict) -> dict:
    if not isinstance(source_payload, dict):
        fallback_payload = normalize_editor_payload_for_confirm(editor_payload)
        if _resolve_process_node(fallback_payload) == "T28":
            fallback_payload = _strip_t28_editor_geometry(fallback_payload)
        return fallback_payload

    normalized_editor = normalize_editor_payload_for_confirm(editor_payload)
    if not isinstance(normalized_editor, dict):
        return source_payload

    result = deepcopy(source_payload)
    incoming_instances = normalized_editor.get("instances")
    incoming_layout_data = normalized_editor.get("layout_data")

    if isinstance(result.get("ring_config"), dict) and isinstance(normalized_editor.get("ring_config"), dict):
        for key in list(result["ring_config"].keys()):
            if key in normalized_editor["ring_config"]:
                result["ring_config"][key] = normalized_editor["ring_config"][key]
        if "process_node" in normalized_editor["ring_config"]:
            result["ring_config"]["process_node"] = normalized_editor["ring_config"]["process_node"]
    elif isinstance(normalized_editor.get("ring_config"), dict):
        result["ring_config"] = dict(normalized_editor["ring_config"])

    if "instances" in result and isinstance(result.get("instances"), list):
        merge_source = incoming_instances if isinstance(incoming_instances, list) else incoming_layout_data
        if isinstance(merge_source, list):
            result["instances"] = merge_instances_with_structure(
                result["instances"],
                merge_source,
                result.get("ring_config", {}),
            )

    if "layout_data" in result and isinstance(result.get("layout_data"), list):
        merge_source = incoming_layout_data if isinstance(incoming_layout_data, list) else incoming_instances
        if isinstance(merge_source, list):
            result["layout_data"] = merge_instances_with_structure(
                result["layout_data"],
                merge_source,
                result.get("ring_config", {}),
            )

    if isinstance(result.get("instances"), list) and isinstance(result.get("layout_data"), list):
        result["layout_data"] = deepcopy(result["instances"])

    if _resolve_process_node(result) == "T28":
        result = _strip_t28_editor_geometry(result)

    return result


def resolve_source_intent_path(target_path: Path) -> Optional[Path]:
    if target_path.name.endswith("_intermediate_editor.json"):
        if target_path.exists():
            return target_path
        origin_name = target_path.name.replace("_intermediate_editor.json", ".json")
        origin_path = target_path.with_name(origin_name)
        if origin_path.exists():
            return origin_path

    if target_path.name.endswith("_confirmed.json"):
        intermediate_name = target_path.name.replace("_confirmed.json", "_intermediate_editor.json")
        intermediate_path = target_path.with_name(intermediate_name)
        if intermediate_path.exists():
            return intermediate_path
        origin_name = target_path.name.replace("_confirmed.json", ".json")
        origin_path = target_path.with_name(origin_name)
        if origin_path.exists():
            return origin_path

    return None
