# Lumen Fleet API Reference

The Lumen Fleet API lets customers monitor and command the robots in their warehouse fleet. This reference covers version 2 of the API, which is served from https://api.lumenrobotics.example/v2. All requests and responses use JSON encoded as UTF-8. Timestamps are ISO 8601 strings in UTC.

The API is stable within a major version. New optional fields may be added to responses at any time, so clients must ignore fields they do not recognise.

## Authentication

Every request must carry a bearer token in the Authorization header. Tokens are created in the customer console under API access, and each token belongs to exactly one organisation. A token is valid for 3600 seconds after it is issued. To obtain a new token, call POST /auth/token with your client id and client secret, and send the new token before the old one expires.

Tokens carry scopes. The scope robots:read allows the GET endpoints for robots and telemetry. The scope robots:command is required to send commands. The scope missions:write is required to create and delete missions. A request that needs a scope the token lacks is rejected with HTTP status 403 and error code E-4030.

Never embed a client secret in a browser or mobile application. Rotate secrets from the console if you suspect they have leaked; the old secret keeps working for 15 minutes after rotation so that deployments can be updated without downtime.

## Conventions

List endpoints are paginated. The default page size is 50 items and the maximum is 200 items, set with the limit query parameter. Responses include a next_cursor field. Pass its value as the cursor parameter to receive the next page. A missing next_cursor means that you have reached the end.

Requests that create resources accept an Idempotency-Key header. If you repeat a request with the same key within 24 hours, the server returns the original response instead of creating a second resource. Keys must be unique per organisation and at most 64 characters long.

All errors have the same shape: an object with the fields code, message and request_id. Please include the request_id when you contact support, because it lets us find the exact request in our logs.

## Robots

GET /robots returns the robots in your fleet. Filter with the query parameters status, site and model. The status filter accepts online, offline, charging and fault.

GET /robots/{id} returns a single robot, including its model, firmware version, battery percentage and last known position. Robot ids look like rb_9f3k2m and never change during the life of a robot, even if it moves between sites.

POST /robots/{id}/commands sends a command to one robot. The supported commands are pause, resume, return_to_dock and identify. The identify command flashes the status ring for ten seconds so that operators can find the robot on the floor. Commands are queued for at most 30 seconds. If the robot does not acknowledge a command within this window, the call fails.

If the target robot is not connected to the fleet service, the command is rejected with error code E-4471 and HTTP status 409. This is the most common error in production. Before retrying, check the robot status with GET /robots/{id}. A robot that stays offline for more than five minutes also raises an alert in the customer console.

Commands to a robot in the fault state are rejected with error code E-4475, except for identify, which is always accepted.

## Missions

A mission is an ordered list of waypoints that a robot drives and a set of actions at each waypoint, such as lifting or lowering a tray.

POST /missions creates a mission and assigns it to a robot or to the fleet. The request body contains a name, an optional robot_id, a priority from 1 to 5 and a list of waypoints. Priority 5 missions preempt lower priority missions. A mission may contain at most 256 waypoints. A body that exceeds this limit is rejected with error code E-4472 and HTTP status 422. Split long routes into several missions that are chained with the follow_up field.

GET /missions lists missions, newest first, and supports the filters state and robot_id. The state of a mission is one of queued, running, paused, completed, failed or cancelled.

DELETE /missions/{id} cancels a queued or running mission. A running mission stops at its next safe point, which is normally within two seconds. Completed missions cannot be deleted, and an attempt returns error code E-4409 with HTTP status 409. The same code is returned when a new mission conflicts with a mission that is already running on the same robot and has the same or higher priority.

If a robot has less than 15 percent charge when a mission is about to start, the mission is not started and the call fails with error code E-5012. Missions are re-queued automatically after the robot has returned to the dock and charged above 30 percent. Operators can override this behaviour in the site settings, but we advise against it.

A mission that leaves the geofence configured for its site is rejected at creation with error code E-5120. Geofences are managed in the customer console, and changes become effective within one minute.

## Telemetry

GET /telemetry/stream opens a server sent events stream with live data for the robots you select. Each event contains the robot id, position, speed, battery percentage and any active warnings. Events are sent once per second per robot. An organisation may have up to 5 concurrent telemetry streams. Opening a sixth stream fails with error code E-4291.

For historical data use GET /telemetry/history, which accepts a robot id and a time range of at most 24 hours per call. The history endpoint returns samples at a resolution of ten seconds. Telemetry is retained for 400 days, after which it is deleted from the history endpoint.

If your client is slow to read, the server buffers events for up to 60 seconds and then closes the stream. Reconnect and resume from the last event id that you processed.

## Webhooks

Webhooks deliver events to your own HTTPS endpoint, so that you do not need to poll. POST /webhooks registers an endpoint and a list of event types, for example mission.completed, mission.failed, robot.offline and robot.fault. The response contains a signing secret, which is shown only once.

Each delivery carries the header X-Lumen-Signature, which is an HMAC SHA 256 of the request body computed with your signing secret. Verify it before trusting the payload. Your endpoint must answer with a 2xx status code within 10 seconds.

If delivery fails, the service retries up to 6 times with exponential backoff, starting at 30 seconds and doubling after each attempt. After the sixth failed attempt the event is dropped and the webhook is marked as degraded in the console. A webhook that fails continuously for 72 hours is disabled.

## Rate limits

Rate limits are applied per organisation and are reported in the response headers X-RateLimit-Limit, X-RateLimit-Remaining and X-RateLimit-Reset.

The Standard plan allows 600 requests per minute. The Enterprise plan allows 3,000 requests per minute. Both plans additionally allow a burst of at most 50 requests within one second. The command endpoint has a separate limit of 20 commands per minute per robot, regardless of plan.

A request that exceeds a limit is rejected with HTTP status 429 and error code E-4290. The response includes a Retry-After header which tells the client how long to wait before the next attempt. Clients should honour this header and add random jitter to avoid synchronised retries. Repeatedly ignoring Retry-After may lead to the token being suspended.

Telemetry streams are not counted against the request limits, but they are subject to the limit of concurrent streams described above.

## Error code reference

The following codes are returned in the code field of an error response. The HTTP status is given where it is fixed.

E-4003 means that the token has expired. The HTTP status is 401. Request a new token and repeat the call.

E-4030 means that the token lacks the required scope. The HTTP status is 403.

E-4409 means a mission conflict, as described in the section on missions. The HTTP status is 409.

E-4471 means that the target robot is offline. The HTTP status is 409.

E-4472 means that a mission has more than 256 waypoints. The HTTP status is 422.

E-4475 means that the robot is in the fault state and cannot accept the command. The HTTP status is 409.

E-4290 means that a rate limit was exceeded. The HTTP status is 429.

E-4291 means that the limit of concurrent telemetry streams was exceeded. The HTTP status is 429.

E-5012 means that the robot battery is too low to start the mission.

E-5120 means that the mission leaves the site geofence. The HTTP status is 422.

E-5301 means that the fleet service is temporarily unavailable. The HTTP status is 503. Retry with exponential backoff.

Codes beginning with E-4 indicate a problem with the request, and codes beginning with E-5 indicate a condition on the robot or in the service. Only E-5301 should be retried automatically without changing the request.

## Sandbox environment

A sandbox is available at https://sandbox.lumenrobotics.example/v2 for integration testing. It simulates a fleet of 12 virtual robots at a virtual site called Demo Hall. Virtual robots respond to commands within one second and never run low on battery unless you ask them to, which you can do by sending the special command drain with a target percentage. The sandbox enforces the same error codes as production, so you can provoke E-4471 by sending the command go_offline to a virtual robot.

Sandbox tokens are separate from production tokens and are valid for 24 hours. Data in the sandbox is reset every night at 03:00 UTC, so do not rely on missions or webhooks persisting across days. Rate limits in the sandbox are lower than in production, at 120 requests per minute.

## Client libraries

Official client libraries exist for Python, TypeScript and Java. They handle token refresh, pagination and retry on rate limit responses automatically. If you write your own client, follow the same rules: refresh tokens a minute before they expire, treat a missing next_cursor as the end of a list, and never retry a command after receiving E-4471 without checking the robot status first.

The libraries expose the request_id of every failed call on the exception object, which makes it easy to attach to support tickets. They are released on the first Tuesday of each month, independently of firmware releases, and the changelog is part of each package.

## Versioning and support

Breaking changes are introduced only in a new major version, and the previous major version is supported for 12 months after the new one is released. Deprecations are announced by email to the technical contacts of the organisation and in the response header Deprecation. The status page at https://status.lumenrobotics.example shows current incidents, and enterprise customers can reach the support team around the clock at api-support@lumenrobotics.example.
