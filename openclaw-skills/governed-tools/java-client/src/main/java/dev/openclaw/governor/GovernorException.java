package dev.openclaw.governor;

/**
 * General exception for Governor client errors (network, parse, HTTP errors).
 */
public class GovernorException extends RuntimeException {

    public GovernorException(String message) {
        super(message);
    }

    public GovernorException(String message, Throwable cause) {
        super(message, cause);
    }
}
