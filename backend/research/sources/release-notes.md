# Lumen Fleet Platform Release Notes

These notes describe the changes in each release of the Lumen fleet platform and robot firmware from v3.2.0 to v3.4.1. Releases are listed with the newest first. Every release is numbered major.minor.patch. Minor releases add features and may change defaults, and patch releases contain only fixes. Each change carries an internal tracking number such as LUM-4012, which you can quote when you contact support.

Robot firmware and the cloud services are released together under the same version number. Robots install firmware over the air while they are idle at the dock, and the previous version stays available for rollback for 7 days.

## v3.4.1

Released 2026-06-09. This patch release fixes problems found after v3.4.0.

- Fixed a crash of the telemetry stream when a client reconnected with an event id older than the buffer. The stream now starts from the oldest event still held in the 60 second buffer (LUM-5120).
- Improved relocalisation in large halls with few features. Robots now request a reflective marker scan after two failed attempts, and the success rate in our test hall rose from 91 percent to 98 percent (LUM-5133).
- The battery health report in the customer console now shows the number of full charge cycles for every pack (LUM-5141).
- Fixed a rounding error that displayed a battery level of 100 percent for robots at 99.5 percent (LUM-5149).
- Corrected the documentation link in the identify command response.

Known issue: the fleet map in the customer console may take up to 20 seconds to refresh on sites with more than 600 robots. A fix is planned.

## v3.4.0

Released 2026-05-12. This minor release raises limits and adds mission chaining.

- The maximum number of waypoints in a mission was raised from 128 to 256. Missions with more waypoints are rejected with E-4472 (LUM-4980).
- Added the follow_up field to POST /missions, which lets a mission start another one automatically when it completes. This makes it possible to split long routes (LUM-4991).
- Added a sandbox environment at sandbox.lumenrobotics.example with 12 virtual robots (LUM-5002).
- Speed zones can now be drawn directly in the customer console, instead of editing the facility map file. Changes take effect within one minute (LUM-5017).
- Idempotency keys are now supported for POST /missions and POST /webhooks. A key is remembered for 24 hours (LUM-5030).
- The webhook delivery log in the console shows the response code of each attempt, which makes it easier to debug failing endpoints (LUM-5044).

Upgrade note: clients that assumed a limit of 128 waypoints do not need to change, but they can now send longer routes.

## v3.3.2

Released 2026-03-19. This is a hotfix for the dispatch outage described in ticket INC-20260314-07.

- Fixed a connection pool leak in the dispatch service that was introduced in v3.3.1. Connections that time out while a robot switches access points are now returned to the pool (LUM-4851).
- Added a regression test that runs the pool for the equivalent of seven days (LUM-4852).
- Added a metric for connection pool occupancy to the monitoring dashboard (LUM-4853).
- Robots are now reconnected in batches of 50 after a service restart, to avoid overloading the dispatch service (LUM-4860).

Customers running v3.3.1 should update as soon as possible. No change is needed on the robots themselves, because the defect was in the service.

## v3.3.1

Released 2026-02-24. This patch release refactors reconnect handling.

- Reconnect logic in the dispatch service was rewritten. The median time for a robot to reconnect after a Wi-Fi roam fell from 14 seconds to 6 seconds (LUM-4702).
- The default low battery threshold at which robots drive to the dock is now 20 percent, previously 25 percent. The setting can still be changed per site (LUM-4718).
- Fixed an issue where the identify command did not flash the status ring on robots that were charging (LUM-4725).
- The error message for E-4475 now includes the fault code of the robot.

## v3.3.0

Released 2026-01-27. This minor release adds a new robot model and tighter limits.

- Added support for the LR7-S1 compact robot. The LR7-S1 requires v3.3.0 or later (LUM-4501).
- Added support for the lift tray LA-118. Robots detect the tray automatically and adjust their speed limits (LUM-4533).
- Introduced a limit of 20 commands per minute per robot on POST /robots/{id}/commands. Requests above the limit are rejected with E-4290 (LUM-4560).
- Introduced the limit of 5 concurrent telemetry streams per organisation. The sixth stream returns E-4291 (LUM-4571).
- Geofences are now enforced when a mission is created, and a mission that leaves the geofence is rejected with E-5120 (LUM-4588).
- Telemetry history queries are limited to 24 hours per call.

Upgrade note: integrations that opened more than 5 telemetry streams must be changed before the upgrade, for example by selecting several robots in one stream.

## v3.2.1

Released 2025-11-20. This patch release fixes issues found in the first weeks of v3.2.0.

- Fixed a localisation drift in long corridors where the lidar saw no features. Robots now use wheel odometry with a higher weight in such sections (LUM-4310).
- Docking contacts are retried up to three times if the first connection fails, which removes most failed charging attempts (LUM-4322).
- Fixed a bug that caused webhook signatures to be computed over a re-serialised body instead of the raw body (LUM-4329).
- Reduced the size of firmware downloads by 35 percent through delta updates (LUM-4337).

## v3.2.0

Released 2025-11-04. This minor release is the first to support the LR7-X2 and the second major version of the API.

- Added support for the LR7-X2 robot. Firmware v3.2.0 is the oldest firmware that can run on the LR7-X2 (LUM-4101).
- API version 2 became generally available. Version 1 remains supported until 2026-11-04 (LUM-4120).
- Added webhooks with HMAC signatures, delivered with up to 6 retries (LUM-4144).
- Added the telemetry history endpoint with a resolution of ten seconds (LUM-4160).
- Added opportunity charging at the dock LD-300, so robots can top up during idle periods. A charge to 80 percent now takes 52 minutes (LUM-4175).
- The token lifetime was shortened from 24 hours to 3600 seconds. Clients must refresh tokens more often (LUM-4188).

Upgrade note: clients that cached tokens for a day will receive E-4003 after an hour and must request a new token.

## Compatibility summary

The LR7-X2 runs on every release from v3.2.0 onwards. The LR7-S1 runs on every release from v3.3.0 onwards, because the smaller battery pack and the different drive controller needed new motion parameters. The lift tray LA-118 is supported from v3.3.0 on both models. Mixed fleets of both models are supported on any release that supports both.

The API features introduced in each release are cumulative. A client written against v3.2.0 keeps working on v3.4.1, with the exceptions listed in the upgrade notes above: shorter token lifetimes from v3.2.0, command and stream limits from v3.3.0, and the higher waypoint limit from v3.4.0, which only relaxes a restriction.

## Security fixes

Security fixes are listed separately so that customers can prioritise upgrades. In v3.2.1 we closed an issue in which a debug port on the robot service panel stayed enabled after commissioning (LUM-4340). In v3.3.0 the signature check for firmware images was moved earlier in the installation process, so that an unsigned image is rejected before it is unpacked (LUM-4595). In v3.4.0 we added rate limiting for failed token requests, which stops password guessing against client secrets (LUM-5051).

No release in this range contains a fix for a vulnerability that was known to be exploited. Details of the severity rating are given in the security policy, which also describes how researchers can report problems.

## Documentation changes

The API reference was reorganised in v3.4.0. Error codes now have their own section, with the HTTP status listed next to each code where it is fixed. The product specification of the LR7 series was updated in v3.3.0 to describe the LR7-S1. We also added worked examples for webhook signature verification in Python, TypeScript and Java to the client libraries, and a troubleshooting page that explains the most common errors, starting with E-4471.

Customers who maintain internal runbooks for their operators should review the pages on robot states, because the status values charging and fault were clarified in v3.3.1. A robot that is charging can accept all commands, while a robot in the fault state accepts only identify.

## Upgrade guidance

Upgrade one minor version at a time on production sites, and test each step in the sandbox first. Skipping a minor version is supported, but then the upgrade notes of all skipped versions apply together. If you manage more than 100 robots, schedule the rollout in waves, so that no more than 25 percent of the fleet installs an update at the same time. Robots that miss an update window install it at the next idle period.

For customers on long term support contracts, the platform team publishes a compatibility matrix with every release. The matrix shows which robot models run on which firmware versions and which API features each version offers. A short summary is printed at the start of each release note, and the full matrix is in the customer console under Fleet settings.

Downgrades are possible for 7 days after an update for robots, but not for cloud services. If you need to roll back after that period, contact support. Rollbacks of the dispatch service are performed by Lumen engineers and are described in the internal runbook.

## Deprecations

API version 1 is deprecated. It will be switched off on 2026-11-04, twelve months after v2 became available. The polling endpoint GET /robots/{id}/events in version 1 has no equivalent in version 2, and customers should use webhooks or the telemetry stream instead.

Firmware older than v3.2.0 is no longer supported on any robot model. Robots running such firmware cannot be enrolled in new sites, and they do not receive security fixes. Contact your account manager to plan the upgrade of older robots.
