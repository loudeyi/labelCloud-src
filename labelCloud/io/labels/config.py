import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import numpy as np
import numpy.typing as npt

from ... import __version__
from ...control.config_manager import config
from ...definitions import (
    Color3f,
    LabelingMode,
    ObjectDetectionFormat,
    SemanticSegmentationFormat,
)
from ...definitions.label_formats.base import BaseLabelFormat
from ...utils.color import hex_to_rgb, rgb_to_hex
from ...utils.logger import warn_once
from ...utils.singleton import SingletonABCMeta
from .exceptions import (
    DefaultIdMismatchException,
    LabelClassNameEmpty,
    LabelIdsNotUniqueException,
    UnknownLabelFormat,
    ZeroLabelException,
)


@dataclass
class ClassConfig:
    name: str
    id: int
    color: Color3f

    @classmethod
    def from_dict(cls, data: dict, fallback_id: int = 0) -> "ClassConfig":
        """Build a ClassConfig from a dict, tolerating missing id/color.

        Hand-written or externally generated `_classes.json` files often contain
        nothing but names; those still have to load instead of raising KeyError.
        """
        name = data["name"]
        color = data.get("color")
        return cls(
            name=name,
            id=int(data.get("id", fallback_id)),
            color=hex_to_rgb(color) if color else LabelConfig.auto_color(fallback_id),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "id": self.id,
            "color": rgb_to_hex(self.color),
        }


class LabelConfig(object, metaclass=SingletonABCMeta):
    #: Palette used for classes that arrive without a colour of their own
    #: (bare-list `_classes.json`, or a class that only appears in label files).
    AUTO_COLORS = (
        "#e6194b",
        "#3cb44b",
        "#4363d8",
        "#f58231",
        "#911eb4",
        "#46f0f0",
        "#f032e6",
        "#bcf60c",
        "#fabebe",
        "#008080",
        "#9a6324",
        "#800000",
    )
    #: Format assumed when no class definition file can be read at all.
    #: labelCloud's own default is `centroid_rel` (radians); every dataset in this
    #: fork writes absolute degrees, and silently reading degrees as radians
    #: corrupts every yaw, so the fallback is `centroid_abs` here.
    FALLBACK_FORMAT = ObjectDetectionFormat.CENTROID_ABS

    def __init__(self) -> None:
        self.classes: List[ClassConfig]
        self.default: int
        self.type: LabelingMode
        self.format: BaseLabelFormat

        if getattr(self, "_loaded", False) != True:
            self.load_config()

    @classmethod
    def auto_color(cls, index: int) -> Color3f:
        return hex_to_rgb(cls.AUTO_COLORS[index % len(cls.AUTO_COLORS)])

    def load_config(self) -> None:
        """Load the class definition file, accepting both known encodings.

        Two shapes exist in the wild:

        * labelCloud's own dict: ``{"classes": [{"name","id","color"}], "default",
          "type", "format", ...}``
        * a bare list of class names, written by the pole/wire auto-labeler:
          ``["pole", "wire"]`` — reading it with ``data["classes"]`` used to raise
          ``TypeError: list indices must be integers`` and crash the app at startup.
        """
        class_definition_path = config.getpath("FILE", "class_definitions")
        data: Optional[Union[dict, list]] = None
        if class_definition_path.exists():
            with class_definition_path.open("r") as stream:
                data = json.load(stream)

        if isinstance(data, dict) and "classes" in data:
            self.classes = [
                ClassConfig.from_dict(c, fallback_id=i)
                for i, c in enumerate(data["classes"])
            ]
            self.default = data.get("default", self.classes[0].id)
            self.type = LabelingMode(data.get("type", LabelingMode.OBJECT_DETECTION))
            self.format = data.get("format", self.FALLBACK_FORMAT)
        elif isinstance(data, list) and data:
            logging.warning(
                "Class definition file %s contains a bare list of names instead of "
                "labelCloud's dict. Importing it as object detection classes with "
                "format '%s'.",
                class_definition_path,
                self.FALLBACK_FORMAT.value,
            )
            self.classes = [
                ClassConfig(str(name), i, color=self.auto_color(i))
                for i, name in enumerate(data)
            ]
            self.default = self.classes[0].id
            self.type = LabelingMode.OBJECT_DETECTION
            self.format = self.FALLBACK_FORMAT
        else:
            logging.warning(
                "No usable class definition found at %s. Falling back to a single "
                "'cart' class with format '%s'. Point the FILE/class_definitions "
                "setting at a valid _classes.json to fix this.",
                class_definition_path,
                self.FALLBACK_FORMAT.value,
            )
            self.classes = [ClassConfig("cart", 0, color=Color3f(1, 0, 0))]
            self.default = 0
            self.type = LabelingMode.OBJECT_DETECTION
            self.format = self.FALLBACK_FORMAT
        self.validate()
        self._loaded = True

    def ensure_class(self, class_name: str) -> bool:
        """Add a class that appears in a label file but not in the config.

        Without this, boxes of an unknown class are drawn in fallback red and
        cannot be selected in the class dropdown. Returns True if it was added.
        """
        if not class_name or class_name in self.get_classes():
            return False
        next_id = max((c.id for c in self.classes), default=-1) + 1
        self.classes.append(
            ClassConfig(class_name, next_id, color=self.auto_color(next_id))
        )
        logging.warning(
            "Class '%s' appeared in a label file but was missing from the class "
            "definition; added it with id %s and saved the config.",
            class_name,
            next_id,
        )
        self.save_config()
        return True

    def save_config(self) -> None:
        self.validate()
        data = {
            "classes": [c.to_dict() for c in self.classes],
            "default": self.default,
            "type": self.type.value,
            "format": self.format,
            "created_with": {"name": "labelCloud", "version": __version__},
        }
        with config.getpath("FILE", "class_definitions").open("w") as stream:
            json.dump(data, stream, indent=4)

    @property
    def nb_of_classes(self) -> int:
        return len(self.classes)

    @property
    def color_map(self) -> npt.NDArray[np.float32]:
        """An (N, 3) array where N is the number of classes and color_map[i] represents the i-th class' rgb color."""
        return np.array([c.color[0:3] for c in self.classes]).astype(np.float32)

    @property
    def class_order(self) -> npt.NDArray[np.int8]:
        """An array lookup table to look up the order of a class id in the label definition."""
        max_class_id = max(c.id for c in self.classes) + 1
        lookup = -np.ones((max_class_id,), dtype=np.int8)
        for order, c in enumerate(self.classes):
            lookup[c.id] = order
        return lookup

    # GETTERS

    def get_classes(self) -> Dict[str, ClassConfig]:
        return {c.name: c for c in self.classes}

    def get_class(self, class_name: str) -> ClassConfig:
        return self.get_classes()[class_name]

    def get_relative_class(self, current_class: str, step: int) -> str:
        """Get class, relative to current by id according to given step"""
        if step == 0:
            return current_class
        id2name = {cc.id: cc.name for cc in self.classes}
        name2id = {v: k for k, v in id2name.items()}
        ids = name2id.values()
        corner_case_id = max(ids) if step < 0 else min(ids)
        current_id = name2id[current_class]
        result_id = current_id + step
        result_id = result_id if result_id in ids else corner_case_id
        return id2name[result_id]

    def get_class_color(self, class_name: str) -> Color3f:
        try:
            return self.get_classes()[class_name].color
        except KeyError:
            warn_once(
                "No color defined for class '%s'!" "Proceeding with red.", class_name
            )
            return hex_to_rgb("#FF0000")

    def has_valid_default_class(self) -> bool:
        for c in self.classes:
            if c.id == self.default:
                return True
        return False

    def get_default_class_name(self) -> str:
        for c in self.classes:
            if c.id == self.default:
                return c.name
        raise DefaultIdMismatchException(
            f"Default class id `{self.default}` is missing in the class list."
        )

    # SETTERS

    def set_first_as_default(self) -> None:
        self.default = self.classes[0].id

    def set_default_class(self, class_name: str) -> None:
        self.default = next((c.id for c in self.classes if c.name == class_name))
        self.save_config()

    def set_class_color(self, class_name: str, color: Color3f) -> None:
        self.get_class(class_name).color = color
        self.save_config()

    def set_label_format(self, label_format: Union[BaseLabelFormat, str]) -> None:
        if label_format not in {
            *ObjectDetectionFormat.list(),
            *SemanticSegmentationFormat.list(),
        }:
            raise UnknownLabelFormat(label_format)

        self.format = label_format  # type: ignore

    # VALIDATION
    def validate(self) -> None:
        if self.nb_of_classes == 0:
            raise ZeroLabelException("At least one label required.")
        # validate the default id presents in the classes
        self.get_default_class_name()
        # validate the ids are unique
        if len({c.id for c in self.classes}) != self.nb_of_classes:
            raise LabelIdsNotUniqueException("Class ids are not unique.")

        for label_class in self.classes:
            if label_class.name == "":
                raise LabelClassNameEmpty("At least one class name is empty.")
