import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ...model import BBox
from . import BaseLabelFormat, abs2rel_rotation, rel2abs_rotation
from .config import LabelConfig


class CentroidFormat(BaseLabelFormat):
    FILE_ENDING = ".json"
    ENCODING = "centroid"

    @staticmethod
    def _read_rotations(rotations: Dict[str, float]) -> List[float]:
        """(x, y, z) of a label entry, by name.

        Reading ``rotations.values()`` made the three axes depend on the key order of
        the file: a document written by another tool with ``z`` first would have loaded
        with the axes swapped. Files that only carry bare numbers keep the old order.
        """
        if all(axis in rotations for axis in ("x", "y", "z")):
            return [float(rotations["x"]), float(rotations["y"]), float(rotations["z"])]
        return [float(value) for value in rotations.values()]

    def import_labels(self, pcd_path: Path) -> List[BBox]:
        labels = []

        label_path = self.label_folder.joinpath(pcd_path.stem + self.FILE_ENDING)
        if label_path.is_file():
            with label_path.open("r") as read_file:
                data = json.load(read_file)

            for label in data["objects"]:
                x = label["centroid"]["x"]
                y = label["centroid"]["y"]
                z = label["centroid"]["z"]
                length = label["dimensions"]["length"]
                width = label["dimensions"]["width"]
                height = label["dimensions"]["height"]
                bbox = BBox(x, y, z, length, width, height)
                rotations = self._read_rotations(label["rotations"])
                if self.relative_rotation:
                    rotations = [rel2abs_rotation(angle) for angle in rotations]
                bbox.set_rotations(*rotations)
                # A class that only exists in the label files must still show up in
                # the dropdown and get a colour instead of falling back to red.
                LabelConfig().ensure_class(label["name"])
                bbox.set_classname(label["name"])
                labels.append(bbox)
            logging.info(
                "Imported %s labels from %s." % (len(data["objects"]), label_path)
            )
        return labels

    def export_labels(self, bboxes: List[BBox], pcd_path: Path) -> None:
        data: Dict[str, Any] = {}
        # Header
        data["folder"] = pcd_path.parent.name
        data["filename"] = pcd_path.name
        data["path"] = str(pcd_path)

        # Labels
        data["objects"] = []
        for bbox in bboxes:
            label: Dict[str, Any] = {}
            label["name"] = bbox.get_classname()
            label["centroid"] = {
                str(axis): self.round_dec(val)
                for axis, val in zip(["x", "y", "z"], bbox.get_center())
            }
            label["dimensions"] = {
                str(dim): self.round_dec(val)
                for dim, val in zip(
                    ["length", "width", "height"], bbox.get_dimensions()
                )
            }
            conv_rotations = bbox.get_rotations()
            if self.relative_rotation:
                conv_rotations = map(abs2rel_rotation, conv_rotations)  # type: ignore

            label["rotations"] = {
                str(axis): self.round_dec(angle)
                for axis, angle in zip(["x", "y", "z"], conv_rotations)
            }
            data["objects"].append(label)

        # Save to JSON
        label_path = self.save_label_to_file(pcd_path, data)
        logging.info(
            f"Exported {len(bboxes)} labels to {label_path} "
            f"in {self.__class__.__name__} formatting!"
        )
