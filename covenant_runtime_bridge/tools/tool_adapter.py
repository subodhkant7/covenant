"""Tool Adapter: Wraps Covenant BaseTool into runtime ITool with ExecutionSafety."""

from typing import Any
from covenant.tools.base import BaseTool
from agent_runtime.core.contracts.tool import ToolSpec
from agent_runtime.core.interfaces.tool import ITool
from agent_runtime.core.state.enums import ExecutionSafety


class CovenantToolAdapter(ITool):
    """
    Adapter enabling existing Covenant BaseTool instances to operate
    as authoritative runtime ITool implementations without code modification.
    """

    def __init__(
        self,
        covenant_tool: BaseTool,
        execution_safety: ExecutionSafety = ExecutionSafety.READ_ONLY,
        risk_level: str = "LOW",
    ):
        self.covenant_tool = covenant_tool
        self._spec = ToolSpec(
            name=covenant_tool.name,
            description=covenant_tool.description,
            parameters_schema=covenant_tool.parameters_schema,
            execution_safety=execution_safety,
            default_risk_level=risk_level,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, **kwargs: Any) -> Any:
        res = await self.covenant_tool.execute(**kwargs)
        if not res.success:
            raise RuntimeError(res.error or f"Covenant tool '{self.spec.name}' failed.")
        return res.data
