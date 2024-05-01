from typing import Any, Dict, List, Literal, Tuple, Type, Union

from pydantic import Field

from inference.enterprise.workflows.entities.base import OutputDefinition
from inference.enterprise.workflows.entities.types import (
    FlowControl,
    InferenceParameterSelector,
    Kind,
    StepOutputSelector,
)
from inference.enterprise.workflows.execution_engine.introspection.connections_discovery import (
    discover_blocks_connections,
)
from inference.enterprise.workflows.execution_engine.introspection.entities import (
    BlockDescription,
    BlockPropertyDefinition,
    BlocksDescription,
)
from inference.enterprise.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)

MY_KIND_1 = Kind(name="1")
MY_KIND_2 = Kind(name="2")
MY_KIND_3 = Kind(name="3")


class Block1Manifest(WorkflowBlockManifest):
    type: Literal["Block1Manifest"]
    name: str = Field(description="name field")
    field_1: Union[bool, InferenceParameterSelector(kind=[MY_KIND_1])]
    field_2: Union[str, StepOutputSelector(kind=[MY_KIND_2])]


class Block1(WorkflowBlock):

    @classmethod
    def get_input_manifest(cls) -> Type[WorkflowBlockManifest]:
        return Block1Manifest

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [OutputDefinition(name="output_1", kind=[MY_KIND_1])]

    async def run_locally(
        self, *args, **kwargs
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], FlowControl]]:
        pass


class Block2Manifest(WorkflowBlockManifest):
    type: Literal["Block2Manifest"]
    name: str = Field(description="name field")
    field_1: List[StepOutputSelector(kind=[MY_KIND_1])]


class Block2(WorkflowBlock):

    @classmethod
    def get_input_manifest(cls) -> Type[WorkflowBlockManifest]:
        return Block2Manifest

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name="output_1", kind=[MY_KIND_3]),
            OutputDefinition(name="output_2", kind=[MY_KIND_2]),
        ]

    async def run_locally(
        self, *args, **kwargs
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], FlowControl]]:
        pass


class Block3Manifest(WorkflowBlockManifest):
    type: Literal["Block2Manifest"]
    name: str = Field(description="name field")
    field_1: str


class Block3(WorkflowBlock):

    @classmethod
    def get_input_manifest(cls) -> Type[WorkflowBlockManifest]:
        return Block3Manifest

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name="output_1", kind=[MY_KIND_1]),
        ]

    async def run_locally(
        self, *args, **kwargs
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], FlowControl]]:
        pass


BLOCK_1_DESCRIPTION = BlockDescription(
    manifest_class=Block1Manifest,
    block_class=Block1,
    block_schema=Block1Manifest.model_json_schema(),
    outputs_manifest=Block1.describe_outputs(),
    block_source="test",
    fully_qualified_block_class_name="some.Block1",
    human_friendly_block_name="Block 1",
    manifest_type_identifier="Block1Manifest",
)
BLOCK_2_DESCRIPTION = BlockDescription(
    manifest_class=Block2Manifest,
    block_class=Block2,
    block_schema=Block2Manifest.model_json_schema(),
    outputs_manifest=Block2.describe_outputs(),
    block_source="test",
    fully_qualified_block_class_name="some.Block2",
    human_friendly_block_name="Block 2",
    manifest_type_identifier="Block2Manifest",
)
BLOCK_3_DESCRIPTION = BlockDescription(
    manifest_class=Block3Manifest,
    block_class=Block3,
    block_schema=Block3Manifest.model_json_schema(),
    outputs_manifest=Block3.describe_outputs(),
    block_source="test",
    fully_qualified_block_class_name="some.Block3",
    human_friendly_block_name="Block 3",
    manifest_type_identifier="Block3Manifest",
)

BLOCKS_DESCRIPTION = BlocksDescription(
    blocks=[BLOCK_1_DESCRIPTION, BLOCK_2_DESCRIPTION, BLOCK_3_DESCRIPTION],
    declared_kinds=[MY_KIND_1, MY_KIND_2, MY_KIND_3],
)


def test_discover_blocks_connections_properly_recognises_where_specific_kinds_can_be_plugged() -> (
    None
):
    # when
    result = discover_blocks_connections(blocks_description=BLOCKS_DESCRIPTION)

    # then
    assert result.kinds_connections == {
        "1": {
            BlockPropertyDefinition(
                block_type=Block1,
                manifest_type_identifier="Block1Manifest",
                property_name="field_1",
                compatible_element="inference_parameter",
                is_list_element=False,
            ),
            BlockPropertyDefinition(
                block_type=Block2,
                manifest_type_identifier="Block2Manifest",
                property_name="field_1",
                compatible_element="step_output",
                is_list_element=True,
            ),
        },
        "2": {
            BlockPropertyDefinition(
                block_type=Block1,
                manifest_type_identifier="Block1Manifest",
                property_name="field_2",
                compatible_element="step_output",
                is_list_element=False,
            ),
        },
        "*": {
            BlockPropertyDefinition(
                block_type=Block1,
                manifest_type_identifier="Block1Manifest",
                property_name="field_1",
                compatible_element="inference_parameter",
                is_list_element=False,
            ),
            BlockPropertyDefinition(
                block_type=Block2,
                manifest_type_identifier="Block2Manifest",
                property_name="field_1",
                compatible_element="step_output",
                is_list_element=True,
            ),
            BlockPropertyDefinition(
                block_type=Block1,
                manifest_type_identifier="Block1Manifest",
                property_name="field_2",
                compatible_element="step_output",
                is_list_element=False,
            ),
        },
    }, "Kinds connections do not match expectations"


def test_discover_blocks_connections_properly_recognises_input_connections() -> None:
    # when
    result = discover_blocks_connections(blocks_description=BLOCKS_DESCRIPTION)

    # then
    assert result.input_connections.property_wise == {
        Block1: {
            "field_1": set(),
            "field_2": {Block2},
        },
        Block2: {"field_1": {Block1, Block3}},
        Block3: {},
    }, "Property-wise input connections are not as expected"
    assert result.input_connections.block_wise == {
        Block1: {Block2},
        Block2: {Block1, Block3},
        Block3: set(),
    }, "Step-wise input connections are not as expected"


def test_discover_blocks_connections_properly_output_input_connections() -> None:
    # when
    result = discover_blocks_connections(blocks_description=BLOCKS_DESCRIPTION)

    # then
    assert result.output_connections.property_wise == {
        Block1: {
            "output_1": {Block2},
        },
        Block2: {
            "output_1": set(),
            "output_2": {Block1},
        },
        Block3: {"output_1": {Block2}},
    }, "Property-wise output connections are not as expected"
    assert result.output_connections.block_wise == {
        Block1: {Block2},
        Block2: {Block1},
        Block3: {Block2},
    }, "Step-wise output connections are not as expected"
