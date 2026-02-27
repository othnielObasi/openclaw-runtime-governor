package dev.openclaw.governor;

/**
 * Thrown when the Governor blocks a tool invocation.
 */
public class GovernorBlockedError extends RuntimeException {

    private final GovernorDecision decision;

    public GovernorBlockedError(String tool, GovernorDecision decision) {
        super("Governor blocked tool '" + tool + "': "
                + (decision.getExplanation() != null ? decision.getExplanation() : "no reason given"));
        this.decision = decision;
    }

    /** The full decision object returned by the Governor. */
    public GovernorDecision getDecision() {
        return decision;
    }
}
