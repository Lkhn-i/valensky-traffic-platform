# Code INDEX

Code root for the LMS lives here: `Сайт обучения/learning_site`.

## Root Goal

Build a Django-based learning platform where a lead can enter from the diagnostic flow,
see Lesson 0 in preview mode, and later unlock the paid course through explicit access grants.

Stage 2 affected product-tree nodes:

- `identity-and-sessions`
- `diagnostic-handoff`
- `course-model`
- `lesson0-preview-access`
- `access-grants`
- `tariff-entitlements`
- `state-and-progress`
- `analytics-events`

Stage 3 added product-tree nodes:

- `diagnostic-preview-entry`
- `course-dashboard`
- `course-player` preview surface
- `analytics-events` for preview interactions

Stage 4 added product-tree nodes:

- `media-delivery`
- `video-provider-adapter`
- `secure-playback`
- `media-analytics`

Stage 5 added product-tree nodes:

- `learner-dashboard`
- `course-player`
- `progress-and-feedback`
- `homework-placeholder`
- `tariff-scoped-course-view`

Stage 6 added product-tree nodes:

- `orders-and-payments`
- `payment-provider-adapter`
- `payment-webhook-placeholder`
- `manual-payment-audit`
- `lead-to-student-conversion`
- `refunds-and-revocation`

Stage 7 added product-tree nodes:

- `operator-dashboard`
- `content-ops`
- `learner-support`
- `homework-review`
- `reporting-console`
- `operator-audit-trail`

Stage 8 added product-tree nodes:

- `notification-queue`
- `notification-templates`
- `notification-retry-dead-letter`
- `bot-outbox`
- `funnel-feedback-events`

Current checkout polish added product-tree nodes:

- `learner-access-status`
- `tariff-selection-surface`
- `checkout-order-page`

Current public preview/login polish added product-tree nodes:

- `unified-login-route`
- `public-preview-entry`
- `course-tariff-price-matrix`
- `ruble-money-formatting`

Current platform gap polish added product-tree nodes:

- `platform-gap-analysis`
- `homework-submission`
- `learner-homework-status`
- `homework-submitted-analytics`

Current platform safety polish added product-tree nodes:

- `protected-lesson-resources`
- `homework-gated-progress`
- `publication-readiness`
- `operator-access-diagnostics`

Current invariants:

- `accounts.User` is the canonical Django user model;
- Robokassa is not connected and no payment secrets are stored;
- `RobokassaPaymentProvider` is a disabled stub; the Stage 6 webhook accepts only the
  local `stage6-valid` test signature;
- `SuccessURL` is UX-only and never grants access;
- access checks live in `access_control.services`, not in UI code;
- preview access is limited to Lesson 0 through `PreviewAccessGrant`;
- paid lessons require an active `AccessGrant`;
- payment-origin access grants are idempotent by non-empty `source_reference`;
- progress updates are idempotent per user and lesson;
- analytics and audit events are append-only by service contract.
- diagnostic handoff token replay cannot create duplicate leads or grants.
- media playback is requested only after `access_control.services.check_access`;
- provider storage fields stay inside `media_library` and do not appear in lesson playback JSON;
- playback tokens are short-lived and stored only as hashes.
- completion is idempotent and cannot erase existing Lesson 0 progress;
- tariff entitlements limit paid lesson access when a tariff has explicit entitlement rows.
- manual payment marking is disabled in production and requires an audit reason.
- refunds/revocations may close paid access, but do not delete `ProgressRecord` history.
- operator routes are role-gated to `super_admin`, `admin` and `manager`.
- operator workflows must call service facades and write `AuditLog` for mutations.
- Telegram/bot delivery is a derived side effect; it never grants access or changes progress.
- notification jobs are idempotent when a `dedupe_key` is supplied.
- failed notification delivery is isolated through retry/dead-letter state.
- bot outbox events are idempotent and are created only after canonical LMS state changes.
- `/login/` is the single manual LMS login for students, managers, admins and super admins.
- `/preview/` and `/learn/courses/gatsa-sales/` can be opened by anonymous visitors; the system
  creates a lead session and grants only Lesson 0 preview access.
- seeded tariffs must match the course program: `Воркшоп` 1 500 ₽, `Базовый` 50 000 ₽,
  `С ментором` 80 000 ₽, `VIP` 120 000 ₽.
- tariff seed refreshes remove stale entitlement rows so old local data cannot keep opening
  modules outside the current tariff matrix.
- learner homework submissions use stable `user:{id}` author identifiers, respect published
  lesson-targeted assignments and attempt limits, and create `homework_submitted` analytics events.
- submitted homework appears in the existing operator review queue; `homework` owns submissions,
  `curriculum` only owns the lesson-page action.
- lesson completion and next-lesson direct URLs are blocked until every published lesson-targeted
  homework assignment on previous lessons has an approved review.
- download lesson blocks must reference `Resource` through `payload.resource_slug`; lesson templates
  never render `Resource.source_url`, `Resource.download_key` or legacy `payload.url` directly.
- `/protected-resources/` resolves a material only after verifying the lesson block binding,
  resource publication status and `access_control.services.check_access`.
- operator publishing cannot move content to `published` when readiness has blocking errors.
- operator learner support diagnostics explain access through the shared access-control service plus
  the homework stop-lesson gate; support UI must not duplicate entitlement rules.

## Tree

```text
learning_site
├── apps/
│   ├── accounts
│   ├── diagnostic_handoff
│   ├── curriculum
│   ├── resources
│   ├── media_library
│   ├── commerce
│   ├── access_control
│   ├── learning_state
│   ├── homework
│   ├── operator
│   ├── events
│   ├── notifications
│   ├── integrations
│   └── shared
├── config/
│   ├── settings/
│   ├── env.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── celery.py
├── static/css/base.css
├── templates/base.html
├── .env.example
├── .env.docker.example
├── .python-version
├── manage.py
├── pyproject.toml
├── uv.lock
├── pytest.ini
├── docker-compose.yml
└── Dockerfile
```

## Entrypoints

| Path | Purpose |
| --- | --- |
| `manage.py` | Django management entrypoint with local settings default |
| `config/settings/base.py` | shared settings, env parsing, DB/cache/Celery/logging baseline |
| `config/settings/local.py` | local development defaults |
| `config/settings/test.py` | isolated test settings |
| `config/settings/production.py` | production/staging hardening stub |
| `config/urls.py` | root URLConf with `/login/`, `/preview/`, `/protected-resources/`, admin and shared routes |
| `config/celery.py` | background worker bootstrap placeholder |
| `apps/shared/views.py` | landing page and healthcheck route |
| `apps/shared/services/health.py` | healthcheck service contract |
| `apps/diagnostic_handoff/views.py` | public preview entry, simulated diagnostic submit and one-time preview entry |
| `apps/curriculum/views.py` | learner dashboard, access/payment status, tariff selection, course preview, lesson player, completion, playback access check |
| `apps/media_library/views.py` | local provider stream proof with playback token validation |
| `apps/commerce/views.py` | checkout JSON placeholder, checkout order page, Robokassa success/fail redirects, disabled ResultURL placeholder |
| `apps/operator/views.py` | operator dashboard, content ops, learner support, homework review, orders and audit routes |

## App Map

| App | Owns | Public surface now |
| --- | --- | --- |
| `accounts` | users, roles, lead profiles, Telegram identity, magic links | `ensure_required_roles`, `assign_role`, `user_has_role`, `get_or_create_lead_from_diagnostic`, `convert_lead_to_student` |
| `diagnostic_handoff` | diagnostic token/session intake and replay policy | `create_diagnostic_handoff`, `resolve_handoff_to_preview_access` |
| `curriculum` | course/module/lesson/block tree, seeded demo tariffs and learner routes | `ORMCurriculumCatalogService`, `ensure_stage3_preview_course`, lesson homework submit route |
| `resources` | downloadable/protected lesson resources | `ORMResourceCatalogService`, `ORMProtectedLessonResourceService`, `protected_lesson_resource` |
| `media_library` | video/audio/document assets, lesson media attachments, playback tickets and provider adapters | `ORMMediaLibraryService`, `PlaybackService`, `LocalPlaybackProvider` |
| `commerce` | orders, normalized payment events, Robokassa placeholder, manual audited payment actions | `create_checkout_placeholder`, `process_robokassa_callback`, `manual_mark_order_paid`, `revoke_order_access` |
| `access_control` | tariffs, entitlements, grants, enrollments | `check_access`, `grant_preview_access`, `grant_paid_access`, `grant_paid_access_once`, `revoke_access_grant`, tariff entitlement filtering |
| `learning_state` | lesson progress per user | `update_progress`, `complete_lesson`, `get_progress_for_lesson`, `list_progress_for_course` |
| `homework` | assignments, submissions, reviews, homework gates | assignment/submission/review service classes, `list_assignments_for_lesson`, `list_assignment_views_for_lesson`, `submit_text_answer`, `check_lesson_homework_gate`, `find_previous_homework_blocker` |
| `operator` | staff-facing workflows, content publication, learner support, homework review, reporting and audit facade | `require_operator_permissions`, `publish_course`, `draft_course`, `get_content_readiness_snapshot`, `get_learner_support_snapshot`, `list_learner_support_items`, `get_homework_review_queue`, `review_homework_submission`, `enqueue_learner_access_link`, `get_operator_dashboard_metrics` |
| `events` | analytics and audit facts | `ORMAnalyticsEventService`, `ORMAuditLogService` |
| `notifications` | queued delivery jobs, templates, retry/dead-letter dispatch | `enqueue_notification`, `enqueue_lesson_zero_entry_notification`, `enqueue_paid_access_notification`, `enqueue_lesson_completed_notification`, `enqueue_homework_reviewed_notification`, `dispatch_notification_job`, `dispatch_pending_notifications`, `list_pending_notifications` |
| `integrations` | external event idempotency and Telegram bot outbox | `record_external_event`, `mark_event_processed`, `enqueue_bot_outbox_event`, `enqueue_bot_outbox_from_notification`, `list_pending_bot_outbox_events`, `mark_outbox_event_sent`, `mark_outbox_event_failed` |
| `shared` | healthcheck, base UI, common foundations | `/`, `/healthz/` |

## Models / Services / Routes

- Identity models: `User`, `Role`, `UserRole`, `UserTelegramIdentity`, `LeadProfile`, `MagicLink`.
- Diagnostic models: `DiagnosticHandoff`.
- Learning content models: `Course`, `Module`, `Lesson`, `LessonBlock`, `Resource`, `MediaAsset`,
  `LessonMediaAttachment`, `PlaybackTicket`.
- Commerce models: `Order`, `PaymentEvent`.
- Access models: `Tariff`, `TariffEntitlement`, `BonusAccess`, `PreviewAccessGrant`, `AccessGrant`, `Enrollment`.
- State models: `ProgressRecord`, `HomeworkAssignment`, `HomeworkSubmission`, `HomeworkReview`.
- Event models: `AnalyticsEvent`, `AuditLog`, `NotificationJob`, `ExternalEvent`, `IntegrationOutboxEvent`.
- Routes:
  - `/` shared landing with public preview and unified login links.
  - `/healthz/` healthcheck.
  - `/login/` single manual login for all roles; redirect target depends on user role/access.
  - `/logout/` ends the session and returns to `/login/`.
  - `/preview/` public trial entry after the external survey; preserves query params like `session_id`.
  - `/accounts/login/` and `/accounts/logout/` legacy redirects to the unified routes.
  - `/diagnostic/preview/simulate/` local simulated diagnostic submit.
  - `/diagnostic/preview/` diagnostic-app public trial alias.
  - `/diagnostic/preview/<token>/` one-time handoff resolver.
  - `/learn/` learner dashboard with enrolled/preview courses, access status, payment status, next lesson and tariff cards.
  - `/learn/courses/<course_slug>/` course preview with locked paid modules and tariff cards.
  - `/learn/lessons/<lesson_id>/` lesson page with access check.
  - `/learn/lessons/<lesson_id>/homework/` posts a learner text answer for a lesson-targeted homework assignment.
  - `/learn/lessons/<lesson_id>/complete/` idempotent lesson completion action.
  - `/learn/lessons/<lesson_id>/playback/` secure playback request after access check.
  - `/learn/playback/tickets/status/` playback token status check.
  - `/learn/lessons/<lesson_id>/video-events/` video analytics intake after access check.
  - `/protected-resources/lessons/<lesson_id>/<resource_slug>/` protected material delivery after
    lesson access and resource-binding checks.
  - `/media-library/playback/<ticket_id>/stream` local provider stream proof.
  - `/commerce/checkout/<tariff_code>/` creates an order and returns disabled checkout metadata for API-style checks.
  - `/commerce/checkout/<tariff_code>/start/` creates a disabled checkout order from learner UI and redirects to the order page.
  - `/commerce/orders/<public_id>/` shows the Robokassa placeholder order page for the order owner.
  - `/commerce/robokassa/success/` records redirect return and sends the learner back to `/learn/`.
  - `/commerce/robokassa/fail/` sends the learner back to `/learn/`.
  - `/webhooks/payments/robokassa/result` placeholder ResultURL; disabled in production.
  - `/operator/` role-gated staff dashboard metrics.
  - `/operator/content/` audited course/module/lesson draft-publish controls.
  - `/operator/learners/` learner/lead lookup.
  - `/operator/learners/<user_id>/` learner support snapshot.
  - `/operator/learners/<user_id>/resend-access-link/` queued access-link notification with audit.
  - `/operator/homework/` manager homework review queue.
  - `/operator/homework/submissions/<submission_id>/review/` review workflow with notification and audit.
  - `/operator/orders/` order/access visibility.
  - `/operator/audit/` audit log browser.
- Tests: service-level tests cover role seeding, preview-vs-paid access, idempotent handoff/progress,
  catalog services, homework services, event logging, notifications, integrations, and healthcheck.
  Stage 3 flow tests cover simulated submit, Lesson 0 access, direct paid lesson denial,
  paid playback denial, replay, missing and expired handoff.
  Stage 4 tests cover Lesson 0 ready playback contract, locked paid playback denial,
  missing/processing media states, expired playback token handling, video progress events
  and local stream token validation.
  Stage 5 tests cover learner dashboard, lesson player rendering, idempotent completion,
  tariff-scoped modules, homework placeholders and progress preservation after paid access.
  Stage 6 tests cover order creation, SuccessURL no-access behavior, valid paid callback
  access grant, duplicate callback idempotency, bad signature, amount mismatch, production
  webhook disablement, manual paid audit, lead-to-student conversion and revoke-without-progress-loss.
  Stage 7 tests cover operator role gating, audited content publication, learner support
  snapshots, access-link notification queueing, homework review decisions and dashboard metrics.
  Stage 8 tests cover idempotent notification enqueueing, retry/dead-letter dispatch,
  Telegram bot outbox idempotency, diagnostic `Урок 0` entry messages, paid access messages,
  lesson completion milestones and the guard that inbound bot events do not mutate canonical LMS state.
  Public preview/login polish tests cover the unified `/login/` route, legacy login redirects,
  anonymous course preview lead creation, public `/preview/` query preservation and current
  tariff names/prices/access durations.
  Checkout polish tests cover seeded tariffs, dashboard payment status, learner checkout start,
  owner-only order page visibility and anonymous redirects through the custom login screen.
  Platform gap polish tests cover learner homework status, text submission, stable author identifiers,
  `homework_submitted` analytics and appearance in the operator review queue.
  Platform safety polish tests cover protected resource access, no raw material key leakage in the
  lesson page, homework-gated completion/direct navigation, publication readiness guards and learner
  access diagnostics in operator support.

## Commands

Assuming Python 3.12 and project root `Сайт обучения/learning_site`:

```bash
rtk uv sync --extra dev
cp .env.example .env
rtk uv run python manage.py migrate
rtk uv run python manage.py ensure_stage3_preview_course
rtk uv run python manage.py runserver
rtk uv run pytest
rtk uv run ruff check .
rtk uv run mypy config apps
rtk docker compose up --build
```

Local `.env.example` uses SQLite and in-memory cache. Docker Compose uses `.env.docker.example`
to point the web container at PostgreSQL and Redis services.

## Change Rules

- Keep real payment provider code and secrets out until the explicit Robokassa integration phase;
  Stage 6 may use only disabled provider stubs and normalized test events.
- Keep video-provider details inside `media_library`; curriculum views may consume only service contracts.
- Keep UI and operator workflows dependent on service facades, not direct cross-app query chains.
- Keep operator views thin; cross-domain aggregation belongs in `apps.operator.services`.
- Keep protected resource resolution inside `apps.resources`; curriculum may render only the
  protected route generated from `payload.resource_slug`.
- Use string FKs or service facades when crossing app boundaries.
- Keep bot/Telegram integrations behind `apps.integrations`; domain apps may publish facts,
  but access, progress and payment state remain canonical in their own service branches.
- Use notification `dedupe_key` and integration `idempotency_key` for every background side effect.
- Add data migrations or seed commands for default roles/tariffs before real users are created.
- Update this `INDEX.md` whenever new routes, models, services, jobs, or commands appear.
