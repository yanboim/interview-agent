"""Request-scoped Agent call/token/cost budgets with ContextVar propagation."""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import monotonic
from typing import Iterator

from app.model_gateway import ModelBudgetExceeded


@dataclass
class AgentBudgetState:
    request_class: str
    price_version: str
    max_calls: int
    max_total_tokens: int
    max_cost_usd: float
    input_usd_per_million: float
    output_usd_per_million: float
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    started_at: float = 0.0
    first_token_ms: int | None = None

    def claim_call(self, purpose: str) -> None:
        if (
            self.calls + 1 > self.max_calls
            or self.input_tokens + self.output_tokens >= self.max_total_tokens
            or self.cost_usd >= self.max_cost_usd
        ):
            raise ModelBudgetExceeded(
                f"{self.request_class} model call budget exhausted before {purpose}"
            )
        self.calls += 1

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        next_input = self.input_tokens + max(0, int(input_tokens))
        next_output = self.output_tokens + max(0, int(output_tokens))
        next_total = next_input + next_output
        next_cost = (
            next_input * self.input_usd_per_million
            + next_output * self.output_usd_per_million
        ) / 1_000_000
        if next_total > self.max_total_tokens or next_cost > self.max_cost_usd:
            raise ModelBudgetExceeded(
                f"{self.request_class} token or cost budget exhausted"
            )
        self.input_tokens = next_input
        self.output_tokens = next_output
        self.cost_usd = next_cost

    def record_first_token(self) -> None:
        if self.first_token_ms is None:
            self.first_token_ms = round((monotonic() - self.started_at) * 1000)

    def snapshot(self) -> dict[str, object]:
        return {
            "request_class": self.request_class,
            "price_version": self.price_version,
            "max_calls": self.max_calls,
            "call_count": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "wall_time_ms": round((monotonic() - self.started_at) * 1000),
            "first_token_ms": self.first_token_ms,
        }


_budget: ContextVar[AgentBudgetState | None] = ContextVar("agent_budget", default=None)


def current_agent_budget() -> AgentBudgetState | None:
    return _budget.get()


@contextmanager
def agent_execution_budget(
    settings: object,
    request_class: str = "chat",
    *,
    max_calls: int | None = None,
) -> Iterator[AgentBudgetState]:
    calls = (
        max_calls
        if max_calls is not None
        else getattr(
            settings, f"agent_{request_class}_max_model_calls",
            getattr(settings, "agent_max_model_calls"),
        )
    )
    tokens = getattr(
        settings, f"agent_{request_class}_max_total_tokens",
        getattr(settings, "agent_max_total_tokens"),
    )
    cost = getattr(
        settings, f"agent_{request_class}_max_cost_usd",
        getattr(settings, "agent_max_cost_usd"),
    )
    state = AgentBudgetState(
        request_class=request_class,
        price_version=str(getattr(settings, "llm_price_version")),
        max_calls=int(calls),
        max_total_tokens=int(tokens),
        max_cost_usd=float(cost),
        input_usd_per_million=float(getattr(settings, "llm_input_usd_per_million")),
        output_usd_per_million=float(getattr(settings, "llm_output_usd_per_million")),
        started_at=monotonic(),
    )
    token: Token[AgentBudgetState | None] = _budget.set(state)
    try:
        yield state
    finally:
        _budget.reset(token)
