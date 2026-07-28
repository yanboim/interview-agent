# Security policy

## Reporting

Report suspected vulnerabilities privately to the repository maintainers or
the private security channel configured by the project owner. Do not open a
public issue containing credentials, exploit steps, private knowledge, user
data, database contents, or undisclosed vulnerability details.

Include:

- affected version or commit;
- environment and prerequisites;
- minimal reproduction without real user data;
- observed and expected behavior;
- potential impact;
- safe mitigation if known.

## Response

Maintainers should acknowledge the report, restrict access to evidence, assess
severity, preserve logs, rotate exposed secrets, prepare a tested fix, and
coordinate disclosure. No response-time commitment is made until an owner and
support policy are formally approved.

Security architecture, threat model, data classification, and test guidance are
indexed in [`docs/security/README.md`](docs/security/README.md).
