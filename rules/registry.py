from __future__ import annotations

from collections.abc import Callable

from schemas import GeometryMetrics, RuleResult

Rule = Callable[[GeometryMetrics], RuleResult | list[RuleResult]]


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule_id: str, rule: Rule) -> None:
        if rule_id in self._rules:
            raise ValueError(f"Duplicate rule ID: {rule_id}")
        self._rules[rule_id] = rule

    def evaluate(self, metrics: GeometryMetrics) -> list[RuleResult]:
        results: list[RuleResult] = []
        for rule_id, rule in self._rules.items():
            value = rule(metrics)
            values = value if isinstance(value, list) else [value]
            if any(result.rule_id != rule_id and not result.rule_id.startswith((f"{rule_id}:", f"{rule_id}."))
                   for result in values):
                raise ValueError(f"Rule {rule_id} returned a mismatched rule ID")
            results.extend(values)
        return results
