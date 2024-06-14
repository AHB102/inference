"""
This is just example, test implementation, please do not assume it being fully functional.
"""

import random
from typing import List, Literal, Type

from pydantic import Field

from inference.core.workflows.entities.base import OutputDefinition
from inference.core.workflows.entities.types import FlowControl, StepSelector
from inference.core.workflows.prototypes.block import (
    BlockResult,
    WorkflowBlock,
    WorkflowBlockManifest,
)


class ABTestManifest(WorkflowBlockManifest):
    type: Literal["ABTest"]
    name: str = Field(description="name field")
    a_step: StepSelector
    b_step: StepSelector

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return []


class ABTestBlock(WorkflowBlock):

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return ABTestManifest

    @classmethod
    def accepts_batch_input(cls) -> bool:
        return False

    async def run(
        self,
        a_step: StepSelector,
        b_step: StepSelector,
    ) -> BlockResult:
        choice = a_step
        if random.random() > 0.5:
            choice = b_step
        return FlowControl(mode="select_step", context=choice)


def load_blocks() -> List[Type[WorkflowBlock]]:
    return [ABTestBlock]
