from copy import deepcopy
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
import supervision as sv
from typing_extensions import Annotated

from inference.core.workflows.constants import PARENT_ID_KEY
from inference.core.workflows.core_steps.common.operators import (
    BINARY_OPERATORS_FUNCTIONS,
    OPERATORS_FUNCTIONS,
    BinaryOperator,
    Operator,
)
from inference.core.workflows.entities.base import OutputDefinition
from inference.core.workflows.entities.types import (
    BATCH_OF_IMAGE_METADATA_KIND,
    BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
    BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
    BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
    BATCH_OF_PARENT_ID_KIND,
    BATCH_OF_PREDICTION_TYPE_KIND,
    FlowControl,
    StepOutputSelector,
)
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)


class DetectionFilterDefinition(BaseModel):
    type: Literal["DetectionFilterDefinition"]
    field_name: str = Field(
        description="Name of detection-like prediction element field to take into filtering expression evaluation: `predictions[<idx>][<field_name>] operator reference_value`",
        examples=[
            "x",
            "y",
            "width",
            "height",
            "confidence",
            "class_name",
            "class_id",
            "points",
            "keypoints",
        ],
    )
    operator: Operator = Field(
        description="Operator in filtering expression: `predictions[<idx>][<field_name>] operator reference_value`",
        examples=["equal", "in"],
    )
    reference_value: Union[float, int, bool, str, list, set] = Field(
        description="Reference value to take into filtering expression evaluation: `predictions[<idx>][<field_name>] operator reference_value`",
        examples=[0.3, 300],
    )


class CompoundDetectionFilterDefinition(BaseModel):
    type: Literal["CompoundDetectionFilterDefinition"]
    left: Annotated[
        Union[DetectionFilterDefinition, "CompoundDetectionFilterDefinition"],
        Field(
            discriminator="type",
            description="Left operand (potentially nested expression) in expression `left bin_operator right`",
        ),
    ]
    operator: BinaryOperator = Field(
        description="Binary operator in expression `left bin_operator right`",
        examples=["and", "or"],
    )
    right: Annotated[
        Union[DetectionFilterDefinition, "CompoundDetectionFilterDefinition"],
        Field(
            discriminator="type",
            description="Right operand (potentially nested expression) in expression `left bin_operator right`",
        ),
    ]


LONG_DESCRIPTION = """
Filter detections from a detections-based block based on specified conditions.

This block is useful to filter out detections that may not be useful for your project. 
You can filter on the basis of:

- Coordinates of a detection
- Confidence of a detection

You can use the following comparison statements in a DetectionFilterBlock:

- `equal` (field value equal to `reference_value`)
- `not_equal`
- `lower_than`
- `greater_than`
- `lower_or_equal_than`
- `greater_or_equal_than`
- `in`
- `str_starts_with`
- `str_ends_with`
- `str_contains`
"""

SHORT_DESCRIPTION = (
    "Filter predictions from detection models based on defined " "conditions."
)


class BlockManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "short_description": SHORT_DESCRIPTION,
            "long_description": LONG_DESCRIPTION,
            "license": "Apache-2.0",
            "block_type": "transformation",
        }
    )
    type: Literal["DetectionFilter"]
    predictions: StepOutputSelector(
        kind=[
            BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
            BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
            BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
        ]
    ) = Field(
        description="Reference to detection-like predictions",
        examples=["$steps.object_detection_model.predictions"],
    )
    filter_definition: Annotated[
        Union[DetectionFilterDefinition, CompoundDetectionFilterDefinition],
        Field(
            discriminator="type",
            description="Definition of a filter expression to be applied for each element of detection-like predictions to decide if element should persist in the output. Can be used for instance to filter-out bounding boxes based on coordinates.",
        ),
    ]
    image_metadata: Annotated[
        StepOutputSelector(kind=[BATCH_OF_IMAGE_METADATA_KIND]),
        Field(
            description="Metadata of image used to create `predictions`. Must be output from the step referred in `predictions` field",
            examples=["$steps.detection.image"],
        ),
    ]
    prediction_type: Annotated[
        Union[StepOutputSelector(kind=[BATCH_OF_PREDICTION_TYPE_KIND])],
        Field(
            description="Type of `predictions`. Must be output from the step referred in `predictions` field",
            examples=["$steps.detection.prediction_type"],
        ),
    ]

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(
                name="predictions",
                kind=[
                    BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
                    BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
                    BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
                ],
            ),
            OutputDefinition(name="image", kind=[BATCH_OF_IMAGE_METADATA_KIND]),
            OutputDefinition(name="parent_id", kind=[BATCH_OF_PARENT_ID_KIND]),
            OutputDefinition(
                name="prediction_type", kind=[BATCH_OF_PREDICTION_TYPE_KIND]
            ),
        ]


class DetectionFilterBlock(WorkflowBlock):

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return BlockManifest

    async def run_locally(
        self,
        predictions: Union[List[Dict[str, Any]], List[sv.Detections]],
        filter_definition: Union[
            DetectionFilterDefinition, CompoundDetectionFilterDefinition
        ],
        image_metadata: List[dict],
        prediction_type: List[str],
    ) -> Union[Union[List[sv.Detections], List[Dict[str, Any]]], Tuple[Union[List[sv.Detections], List[Dict[str, Any]]], FlowControl]]:
        filter_callable = build_filter_callable(definition=filter_definition)
        result_predictions, result_parent_ids = [], []
        for detections in predictions:
            if isinstance(detections, list):
                filtered_detections = [d for d in detections if filter_callable(d[filter_definition.field_name])]
                filtered_parent_ids = [d[PARENT_ID_KEY] for d in filtered_detections]
            else:
                filtered_detections = detections[[filter_callable(detections[i]) for i in range(len(detections))]]
                filtered_parent_ids = filtered_detections[PARENT_ID_KEY].tolist()
            result_predictions.append(deepcopy(filtered_detections))
            result_parent_ids.append(filtered_parent_ids)
        return [
            {
                "predictions": prediction,
                PARENT_ID_KEY: parent_ids,
                "image": image,
                "prediction_type": single_prediction_type,
            }
            for prediction, parent_ids, image, single_prediction_type in zip(
                result_predictions, result_parent_ids, image_metadata, prediction_type            )
        ]


def get_value(detection: Union[Dict[str, Any], sv.Detections], field_name: str):
    if isinstance(detection, dict):
        return detection[field_name]
    else:
        if hasattr(detection, field_name):
            val: Optional[np.ndarray] = getattr(detection, field_name)
            if val:
                return val[0]
            return None
        elif hasattr(detection, "data") and field_name in detection.data:
            val: Optional[np.ndarray] = detection[field_name]
            if val:
                return val[0]
            return None
        else:
            raise ValueError(f"Property name '{field_name}' specified within filter definition "
                              "could not be found in predictions.")


def build_filter_callable(
    definition: Union[DetectionFilterDefinition, CompoundDetectionFilterDefinition],
) -> Callable[[Union[Dict[str, Any], sv.Detections]], bool]:
    if definition.type == "CompoundDetectionFilterDefinition":
        left_callable = build_filter_callable(definition=definition.left)
        right_callable = build_filter_callable(definition=definition.right)
        binary_operator = BINARY_OPERATORS_FUNCTIONS[definition.operator]
        return lambda e: binary_operator(left_callable(e), right_callable(e))
    if definition.type == "DetectionFilterDefinition":
        operator = OPERATORS_FUNCTIONS[definition.operator]
        return lambda e: operator(get_value(e, definition.field_name), definition.reference_value)
    raise ValueError(
        f"Detected filter definition of type {definition.type} which is unknown"
    )
