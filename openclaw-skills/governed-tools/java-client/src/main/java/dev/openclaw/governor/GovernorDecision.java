package dev.openclaw.governor;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Decision returned by the Governor for a tool evaluation.
 */
public class GovernorDecision {

    private final String decision;
    private final double riskScore;
    private final String explanation;
    private final List<String> policyIds;
    private final Map<String, Object> modifiedArgs;
    private final Map<String, Object> raw;

    public GovernorDecision(
            String decision,
            double riskScore,
            String explanation,
            List<String> policyIds,
            Map<String, Object> modifiedArgs,
            Map<String, Object> raw) {
        this.decision = decision;
        this.riskScore = riskScore;
        this.explanation = explanation;
        this.policyIds = policyIds != null ? policyIds : Collections.emptyList();
        this.modifiedArgs = modifiedArgs;
        this.raw = raw != null ? raw : Collections.emptyMap();
    }

    /** "allow", "block", or "review". */
    public String getDecision() { return decision; }

    /** Numeric risk score (0–100). */
    public double getRiskScore() { return riskScore; }

    /** Human-readable explanation. */
    public String getExplanation() { return explanation; }

    /** IDs of policies that triggered. */
    public List<String> getPolicyIds() { return policyIds; }

    /** Modified arguments (if the Governor rewrote them), or null. */
    public Map<String, Object> getModifiedArgs() { return modifiedArgs; }

    /** The full raw JSON response as a Map. */
    public Map<String, Object> getRaw() { return raw; }

    @Override
    public String toString() {
        return "GovernorDecision{decision='" + decision + "', riskScore=" + riskScore
                + ", explanation='" + explanation + "'}";
    }
}
