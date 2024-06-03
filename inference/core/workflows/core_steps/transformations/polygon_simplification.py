from typing import Any, List, Literal, Tuple, Type, Union

import cv2 as cv
import numpy as np
import supervision as sv
from pydantic import ConfigDict, Field

from inference.core.workflows.entities.base import OutputDefinition
from inference.core.workflows.entities.types import (
    BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
    INTEGER_KIND,
    LIST_OF_VALUES_KIND,
    STRING_KIND,
    FlowControl,
    StepOutputSelector,
    WorkflowParameterSelector,
)
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)

OUTPUT_KEY: str = "simplified_polygons"
TYPE: str = "PolygonSimplification"
SHORT_DESCRIPTION = (
    "Simplify polygons so they are geometrically convex "
    "and simplify them to contain only requested amount of vertices"
)
LONG_DESCRIPTION = """
The `PolygonSimplificationBlock` is a transformer block designed to simplify polygon
so it's geometrically convex and then reduce number of vertices to requested amount.
This block is best suited when shape of underlying object needs to be detected
and there are other objects on top of that shape (i.e. basketball field during the game
or chess board with pieces)
"""


class PolygonSimplificationManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "short_description": SHORT_DESCRIPTION,
            "long_description": LONG_DESCRIPTION,
            "license": "Apache-2.0",
            "block_type": "transformation",
        }
    )
    type: Literal[f"{TYPE}"]
    predictions: StepOutputSelector(
        kind=[
            BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
        ]
    ) = Field(  # type: ignore
        description="",
        examples=[],
    )
    simplify_class_name: Union[str, WorkflowParameterSelector(kind=[STRING_KIND])] = Field(  # type: ignore
        description="Simplify polygons for all objects of given class name",
    )
    required_number_of_vertices: Union[int, WorkflowParameterSelector(kind=[INTEGER_KIND])] = Field(  # type: ignore
        description="Keep reducing contour until number of vertices matches this number",
    )

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name=OUTPUT_KEY, kind=[LIST_OF_VALUES_KIND]),
        ]


def calculate_simplified_polygon(
    mask: np.ndarray, required_number_of_vertices: int, max_steps: int = 1000
) -> np.array:
    contours = sv.mask_to_polygons(mask)
    largest_contour = max(contours, key=len)

    # https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html#ga014b28e56cb8854c0de4a211cb2be656
    convex_contour = cv.convexHull(
        points=largest_contour,
        returnPoints=True,
        clockwise=True,
    )
    # https://docs.opencv.org/4.9.0/d3/dc0/group__imgproc__shape.html#ga8d26483c636be6b35c3ec6335798a47c
    perimeter = cv.arcLength(curve=convex_contour, closed=True)
    upper_epsilon = perimeter
    lower_epsilon = 0.0000001
    epsilon = lower_epsilon + upper_epsilon / 2
    # https://docs.opencv.org/4.9.0/d3/dc0/group__imgproc__shape.html#ga0012a5fdaea70b8a9970165d98722b4c
    simplified_polygon = cv.approxPolyDP(
        curve=convex_contour, epsilon=epsilon, closed=True
    )
    for _ in range(max_steps):
        if len(simplified_polygon) == required_number_of_vertices:
            break
        if len(simplified_polygon) > required_number_of_vertices:
            lower_epsilon = epsilon
        else:
            upper_epsilon = epsilon
        epsilon = lower_epsilon + (upper_epsilon - lower_epsilon) / 2
        simplified_polygon = cv.approxPolyDP(
            curve=convex_contour, epsilon=epsilon, closed=True
        )
    while len(simplified_polygon.shape) > 2:
        simplified_polygon = np.concatenate(simplified_polygon)
    return simplified_polygon.tolist()


class PolygonSimplificationBlock(WorkflowBlock):
    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return PolygonSimplificationManifest

    async def run_locally(
        self,
        predictions: List[sv.Detections],
        required_number_of_vertices: int,
        simplify_class_name: str,
    ) -> Tuple[List[Any], FlowControl]:
        result = []
        for detections in predictions:
            filtered_detections = detections[
                detections["class_name"] == simplify_class_name
            ]
            simplified_polygons = []
            for mask in filtered_detections.mask:
                simplified_polygon = calculate_simplified_polygon(
                    mask=mask,
                    required_number_of_vertices=required_number_of_vertices,
                )
                if len(simplified_polygon) != required_number_of_vertices:
                    continue
                simplified_polygons.append(simplified_polygon)
            result.append({OUTPUT_KEY: simplified_polygons})
        return result, FlowControl(mode="pass")
