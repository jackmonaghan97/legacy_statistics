"""
How the template's raw breakdowns roll up into the Justice Counts / BJA categories.

One place for these so the BJA and Justice Counts exports cannot drift apart again.
Keyed by breakdown_category because 'technical' / 'new offense' mean different things
under revocations and under reported violations.
"""

# template breakdown_category -> (JC metric, JC breakdown_category name)
METRICS = {
    "population":          ("population",  "supervision_type"),
    "discharge":           ("discharges",  "discharges_type"),
    "reported violations": ("violations",  "violation_type"),
    "court actions":       ("revocations", "revocations_type"),
    "new cases":           ("new_cases",   "case_type"),
}

BREAKDOWNS = {
    "population": {
        "active":          "People on Active Supervision",
        "home confinment": "People on Active Supervision",
        "supervision":     "People on Active Supervision",
        "admin":           "People on Administrative Supervision",
    },
    "discharge": {
        "scheduled termination": "Successful Discharges from Supervision",
        "early termination":     "Successful Discharges from Supervision",
        "revoked-new":           "Unsuccessful Discharges from Supervision",
        "revoked-technical":     "Unsuccessful Discharges from Supervision",
        "absconder/warrant":     "Unsuccessful Discharges from Supervision",
        "alt doc commit":        "Unsuccessful Discharges from Supervision",
        "unsatisfactory":        "Unsuccessful Discharges from Supervision",
        "conditional disch":     "Neutral Discharges from Supervision",
        "transferred":           "Other Discharges from Supervision",
        "other":                 "Other Discharges from Supervision",
    },
    "court actions": {           # revocations: the template metric names the violation type
        "technical":   "Revocations for Technical Violations",
        "new offense": "Revocations for New Offenses",
    },
    "reported violations": {
        "technical":   "Technical Violations",
        "new offense": "New Offense Violations",
    },
}
