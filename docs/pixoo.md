# What a Pixoo 64 will actually take

Everything below was measured on a real device, because reasoning about it
produced three theories and no certainty. If you are about to turn the refresh
rate up, this is the page that tells you how much room you have.

## Where it gives up

A script pushed pages at a steadily shortening interval and logged the interval,
the cumulative push count and the device's `PicId` at every step.

| Interval | Pushes/s | Result |
|---|---|---|
| 2.06 → 0.35 s | 0.5 → 2.9 | survived, both runs |
| 0.24 s | 4.2 | survived, 40 pushes |
| 0.17 s | 5.9 | survived, 40 pushes |
| 0.12 s | 8.3 | survived, 40 pushes |
| **0.08 s** | **12.5** | **froze, after 380 cumulative pushes** |

The vendor's own guidance is one push per second. That turns out to be twelve
times under where this device actually breaks — so it is a safety margin, not a
hard ceiling, and there is real room above it.

## It freezes, it does not crash

This is the part worth knowing, because it changes how you detect the failure.

At 0.08 s the device kept answering `Draw/GetHttpGifId` with `error_code: 0`
while **`PicId` stopped moving entirely**. It accepts the HTTP request and then
silently never draws it. Confirmed from both ends at once: the on-screen counter
stopped at 341 while the pushing script's own log ran on to 380. Those ~39
pushes were accepted over HTTP and never rendered.

A freeze does not heal itself. An independent probe recorded `PicId 24,
error_code 0` unchanged for 79 seconds, ending only because the device was
rebooted by hand.

A real reboot looks nothing like it — `Errno 111 Connection refused`, the entity
going `unavailable`, and recovery on its own in about 30 seconds. Three tells,
all of them opposite:

| | Reboot | Freeze |
|---|---|---|
| HTTP | refuses | answers normally |
| Visible to Home Assistant | `unavailable` | **nothing at all** |
| Recovery | itself, ~30 s | manual reboot only |

The light entity stays `on` right through a freeze, so **Home Assistant cannot
see this failure**. Two consecutive `Draw/GetHttpGifId` calls with an unchanged
`PicId`, while something is definitely pushing, is the only reliable test.

Recovery is `Device/SysReboot` over HTTP; it comes back in about 20 seconds with
`PicId: 1`.

## Reboots happen on their own

Twice in sixteen minutes on 2026-08-30, while something was pushing at one page
every six to ten seconds — nowhere near the rate that breaks it. Both times the
entity went `unavailable` and was back about 25 seconds later without anyone
touching it:

```
12:48:41  unavailable      13:04:54  unavailable
12:49:07  on   (26 s)      13:05:15  on   (21 s)
```

In the log it is a connect timeout, not a refusal to draw. The library that
talks to the device says the same thing plainly: *"sometime the Pixoo will
reboot when sending a command. No way to fix this at the moment."*

Which means anything that draws to one should survive it. In an automation that
is `continue_on_error: true` on the service call: a reboot then costs one
frame, instead of a stack trace and an aborted run that leaves the rest of the
sequence undone.

## What that means for your intervals

Rate limiting is a *safety* limit, so pick a number well under the break and
stop worrying about it. The blueprint in this repo defaults to a one-second
floor, twelve times under the measured failure. A two-second refresh on the
render automation sits twenty-five times under it.

Two things that are easy to get wrong:

**Spacing and overwriting are different problems.** A floor stops two pushes
landing on the device at once. It does nothing about one screen overwriting
another that was meant to stay up — that needs whoever draws to check whether
something more important is on screen, and no interval will fix it for you.

**A rate limit may delay a render; it may not forget one.** Run the script
`mode: single` and a trigger that arrives during a push is dropped on the floor,
which is exactly how a state change ends up appearing a minute late. `queued`
with `max: 2` delays instead of dropping.

## Two smaller traps

The `divoom_pixoo` integration opens image paths with PIL and only catches
template and network errors. A path that does not exist therefore does not give
you a missing picture — it kills the whole page. Resolve paths where you can
check them, not in a Jinja template, and always have a real file to fall back
on.

It also calls `Image.open()` without `seek()`, so an animated GIF shows you
frame 0 and nothing else. What does work is templating `image_path`, which lets
you swap the file per render and flip through frames that way.
