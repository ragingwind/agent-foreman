"""What every agent adapter shares."""


class TokenMissing(Exception):
    """The gateway's token variable is not set where the agent starts."""

    def __init__(self, variable):
        super().__init__(variable)
        self.variable = variable


class NoTranscript(Exception):
    """No transcript for the session on this machine."""


# Names an adapter module defines. tests/test_adapters.py checks every adapter.
REQUIRED = [
    "KIND",            # the name profiles use in `agent`
    "HERDR_KIND",      # the kind `herdr agent start --kind` and herdr's detection use
    "EXECUTABLE",      # the program launch.py replaces itself with
    "command",         # (cfg, profile name, ...) -> (argv, variables to set, variable names to clear)
    "parse_print",     # prompt-mode stdout -> {"ok", "result", "session_id", "cost", "denials"}
    "bundle_layout",   # {skill name: {relative path: bytes}} -> {bundle path: bytes}, manifest included
    "skill_name",      # skill ref -> the name the agent calls it by
    "last_answers",    # (session id, n) -> the final text of the last n turns
    "CHECKOUT_PROBE",  # Python source; prints {"checkout", "ready", "reason"} for a path
]
