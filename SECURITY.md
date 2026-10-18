# Security policy

## Supported versions

immich-steward is in early development. Security fixes are made only for the latest release.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub:
[Report a vulnerability](https://github.com/Ivamic/immich-steward/security/advisories/new)
(the **Security** tab of the repository → **Report a vulnerability**).

Please include:

- the version of immich-steward and of Immich;
- what an attacker can do and under which conditions (for example, network access to the core,
  a signed-in user of another account, a worker token);
- steps to reproduce or a proof of concept.

You can expect a first answer within a week. Once the problem is fixed and a release is out,
the advisory is published, with credit to you if you wish.

## Scope

Of particular interest: access to another user's photos or Immich API keys, sessions, the
worker API and its token, and anything that writes to Immich without the user's confirmation.
