import logging
from pathlib import Path
from typing import List, Optional

from ..io.labels import BaseLabelFormat, CentroidFormat, KittiFormat, VerticesFormat
from ..io.labels.config import LabelConfig
from ..io.labels.detection import FormatGuard, describe_label_file
from ..model import BBox
from .config_manager import config


def get_label_strategy(export_format: str, label_folder: Path) -> "BaseLabelFormat":
    if export_format == "vertices":
        return VerticesFormat(label_folder, LabelManager.EXPORT_PRECISION)
    elif export_format == "centroid_rel":
        return CentroidFormat(
            label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=True
        )
    elif export_format == "kitti":
        return KittiFormat(
            label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=True
        )
    elif export_format == "kitti_untransformed":
        return KittiFormat(
            label_folder,
            LabelManager.EXPORT_PRECISION,
            relative_rotation=True,
            transformed=False,
        )
    elif export_format != "centroid_abs":
        logging.warning(
            f"Unknown export strategy '{export_format}'. Proceeding with default (centroid_abs)!"
        )
    return CentroidFormat(
        label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=False
    )


class LabelManager(object):
    STD_LABEL_FORMAT = LabelConfig().format
    EXPORT_PRECISION = config.getint("LABEL", "export_precision")

    def __init__(
        self,
        strategy: str = STD_LABEL_FORMAT,
        path_to_label_folder: Optional[Path] = None,
    ) -> None:
        self.label_folder = path_to_label_folder or config.getpath(
            "FILE", "label_folder"
        )
        if not self.label_folder.is_dir():
            self.label_folder.mkdir(parents=True)

        self.label_strategy = get_label_strategy(strategy, self.label_folder)
        #: Keeps label files whose encoding differs from what we write from being
        #: silently rewritten (see io/labels/detection.py).
        self.format_guard = FormatGuard(
            self.label_folder, self.label_strategy.FILE_ENDING
        )

    def import_labels(self, pcd_path: Path) -> List[BBox]:
        label_path = self.label_folder.joinpath(
            pcd_path.stem + self.label_strategy.FILE_ENDING
        )
        info = describe_label_file(label_path)
        self.format_guard.note_read(label_path, str(info["encoding"]))

        if info["exists"] and info["encoding"] != self.label_strategy.ENCODING:
            logging.error(
                "Label file %s is stored as '%s' but this session reads '%s'. "
                "The frame is shown without boxes and will NOT be overwritten; "
                "point FILE/class_definitions at a matching class config (or use "
                "the matching label folder) to edit these labels.",
                label_path.name,
                info["encoding"],
                self.label_strategy.ENCODING,
            )
            self.format_guard.refusals.add(label_path.stem)
            return []

        if (
            info["rotation_unit"] == "degrees"
            and getattr(self.label_strategy, "ROTATION_UNIT", "degrees") == "radians"
        ):
            # Provable mismatch: the file holds an angle outside (-pi, pi], so it is in
            # degrees, while this session converts radians on read. The boxes load with
            # the wrong heading — say so once, loudly, instead of showing them silently.
            self.format_guard.mismatches.add(label_path.stem)
            logging.error(
                "Label file %s stores rotations in degrees, but this session reads "
                "radians (%s). The boxes of this folder are rotated wrongly; point "
                "FILE/class_definitions at a class config with format 'centroid_abs'.",
                label_path.name,
                self.label_strategy.__class__.__name__,
            )

        try:
            return self.label_strategy.import_labels(pcd_path)
        except KeyError as key_error:
            logging.warning("Found a key error with %s in the dictionary." % key_error)
            logging.warning(
                "Could not import labels, please check the consistency of the label format."
            )
            return []
        except AttributeError as attribute_error:
            logging.warning(
                "Attribute Error: %s. Expected a dictionary." % attribute_error
            )
            logging.warning(
                "Could not import labels, please check the consistency of the label format."
            )
            return []

    def export_labels(self, pcd_path: Path, bboxes: List[BBox]) -> bool:
        """Write the labels of one frame. Returns False when nothing was written.

        The only reason not to write is the format guard refusing to convert a file
        that holds a different encoding. Reporting that as a *failure* matters: the
        caller used to mark the frame as saved and never retried, so the edits stayed
        in memory until the session ended.
        """
        label_path = self.label_folder.joinpath(
            pcd_path.stem + self.label_strategy.FILE_ENDING
        )
        other_encoding = self.format_guard.expected_encoding(
            pcd_path.stem, self.label_strategy.ENCODING
        )
        if other_encoding is not None:
            logging.error(
                "Refusing to overwrite %s: it holds '%s' labels while this session "
                "writes '%s'. Re-open it with a matching class config, or convert "
                "the folder first. Nothing was written.",
                label_path.name,
                other_encoding,
                self.label_strategy.ENCODING,
            )
            return False

        backup = self.format_guard.backup(label_path)
        if backup is not None:
            logging.info("Backed up %s to %s before overwriting.", label_path.name, backup)

        self.label_strategy.export_labels(bboxes, pcd_path)
        return True
