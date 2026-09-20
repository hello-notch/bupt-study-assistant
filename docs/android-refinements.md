# Android interaction and reminder changes

## UI

- Empty weeks render all 14 timetable sections. Weeks with courses still trim
  trailing empty sections and collapse interior gaps.
- The week number sits between the navigation arrows. Add/import actions share
  the same compact header.
- Native Back dispatches to Vue before leaving the activity. Course editing
  returns to course details; task, import, homework, account and AI dialogs close
  before returning through page navigation history.
- The Android inset background and status/navigation bar icon appearance follow
  the effective light/dark theme. Android uses a solid application background.
- The thinking control sits immediately before Send on mobile.
- Short mobile viewports (including the open keyboard) compact the assistant
  header, temporarily hide secondary navigation and cap the input height so
  attachments and long drafts cannot push Send behind the bottom navigation.

## Reminder lifecycle

Vue synchronizes a bounded queue of future task/course occurrences whenever
tasks, courses, account visibility or reminder preferences change. Quiet hours
are evaluated at the scheduled reminder time, including per-task overrides.
System-notification opt-out clears the native queue.

`ReminderReceiver` persists the queue in app-private preferences and schedules
only its earliest entry with AlarmManager's user-visible alarm-clock API. The
system may show the next reminder in its next-alarm indicator. No WebView or JavaScript timer is
needed for system delivery. Delivered entries are removed before scheduling the
next alarm; stable notification tags prevent duplicate notification cards.
The manifest receiver restores the queue on boot, package replacement, clock
changes and exact-alarm permission grants. Activity resume also reconciles it.

POST_NOTIFICATIONS and exact-alarm access are separate permissions. Settings
contains a native permission check. If exact-alarm access is unavailable, the
fallback is an inexact idle-capable alarm and may be delayed. OEM background
restrictions and explicitly force-stopping the app remain OS constraints.
Normal silent reminders use a separate notification channel; users can further
control each channel in Android settings.

Android no longer posts duplicate system notifications from the foreground
five-second timer; that timer still maintains the in-app message list.

## Assistant attachments

Official DeepSeek documentation checked on 2026-09-18:

- `https://api-docs.deepseek.com/guides/vision`
- `https://api-docs.deepseek.com/guides/files_api`

Flash and its legacy Flash aliases accept image input. V4 Pro is not advertised
as image-capable by this client. Add `deepseek-flash` without invalidating saved
legacy model names. Quick mode explicitly sends disabled thinking.

The picker accepts PNG/JPEG/WebP. Images are decoded, downscaled to a maximum
2048-pixel side and encoded as JPEG, capped at 1 MB each and two per message.
Original files above 20 MB are rejected before decoding. Selection errors are
reported; asynchronous selection cannot attach an image to another conversation.
The native runtime rechecks role, model capability, MIME/data URL, decoded size,
file signature, per-message count and total image bytes before contacting the API.

DeepSeek's documented Files API currently stores image formats, not arbitrary
PDF/Word documents. This change uses inline image messages and does not expose
an unsupported general-document upload control.

## Verification

- `pnpm --dir client test`
- `node scripts/mobile-ui.test.cjs`
- `node scripts/homework-ui.test.cjs`
- `scripts/build-android.ps1`
- `scripts/android-ui-regression.cjs` with `ANDROID_SERIAL` and a current WebView
  CDP forward at port 9224. Modes: `layout`, `reminder`, `image`, `image-send`,
  `gesture`, `theme`, `cleanup`.

The reminder mode creates a clearly named temporary test task and waits in the
background. Remove only those test tasks after collecting delivery evidence.
Do not claim background delivery from a successful build or alarm registration
alone. APK hashes and device results must refer to the final installed build.

### Verified build, 2026-09-18

- Debug APK: `YouXueBan-1.1.0-Android-test.apk`, version 1.1.0 / 11001.
- SHA-256: `1DB4C1265312C92EB911D52424A79AFDB46C011CB999F6C38AF686449095A4A1`.
- Covered by 37 passing unit tests, both UI regression scripts, TypeScript,
  Vite and Gradle builds.
- On the connected 2407FRK8EC handset: startup, all empty-week rows, centered
  import icon, add/edit/import Back transitions, the dismissed-editor edge case,
  right-edge system Back gesture and light/dark native system bars passed.
- A synthetic blue-square image was decoded and previewed in the WebView,
  sent through the native runtime, and correctly described by the real model.
  The system photo picker opened. Short-height/long-input/attachment Send
  hit-testing also passed at 320px and 390px widths.
- The final installed APK delivered a new task notification while the app stayed
  in the background. The receiver log and matching notification tag were
  observed before reopening the app. Temporary tasks, messages and conversations
  were removed; the original theme and user data were retained.
- Device reboot, long-duration deep idle, all other OEMs and all permission-
  denial transitions were not exercised. This is a Debug test build, not a
  production-signed release.
