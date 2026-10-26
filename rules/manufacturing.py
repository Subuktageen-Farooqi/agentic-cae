from schemas import GeometryMetrics, RuleResult, RuleStatus


def scaffolded_rules(metrics: GeometryMetrics) -> list[RuleResult]:
    return [
        RuleResult(rule_id="manufacturing.minimum_wall_thickness", status=RuleStatus.NOT_IMPLEMENTED,
                   message="Minimum wall thickness measurement is not implemented"),
        RuleResult(rule_id="manufacturing.process_constraints", status=RuleStatus.NOT_IMPLEMENTED,
                   message="Material-, equipment- and supplier-specific process checks are not implemented"),
        RuleResult(rule_id="mechanical.application_specific", status=RuleStatus.NOT_IMPLEMENTED,
                   message="Application-specific mechanical rules are not implemented"),
        RuleResult(rule_id="requirements.additional_verification", status=RuleStatus.NOT_IMPLEMENTED,
                   message="No additional requirement verifier is registered for this prototype example"),
    ]
