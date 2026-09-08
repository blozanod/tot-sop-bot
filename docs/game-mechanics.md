# Game mechanics — please fill in

Prose, bullets, fragments, whatever. Tidiness doesn't matter; accuracy does.

I use this to write the plain-English description attached to every button state,
so your run trace reads like

> `10:47` — Elevator 2: Dispatch turned green (loaded and the track is clear)

instead of `ELEV2_DISPATCH=GREEN`. That trace is the raw material for your SOP.

**Anything you're unsure about, say so** and I'll describe only what's visible on
screen rather than asserting a mechanism. A hedge is cheap; a confident wrong
description propagates straight into the written procedure.

---

## Guests

1. Where do guests come from, and what's the difference between **Front Waiting**
   and **Back Waiting**? Do you control which queue feeds which TV room?

2. What is the **Visitor Counter** counting — total served, currently inside, or
   something else?

3. Do guests **leave** if they wait too long? Is there a penalty, or do you just
   lose the points you'd have earned?

## TV rooms

4. What does **Load TV Room** actually do — move a fixed batch in, fill to
   capacity, or open the doors and let them trickle?

5. **Capacity?** The screenshot shows `Loaded: 2` — is that out of a fixed max?

6. **Entrance** vs **Exit** — which physical door is which, and does
   **Automatic Doors** operate them for you? Is auto better or worse for scoring?

7. **Start Preshow** — what must be true before you can start it? How long does it
   run? What happens if you start it with a half-full room: is that wasted
   capacity, or does it still score normally?

8. **Unload TV Room** — where do guests go? Straight to an elevator queue, or to a
   shared pool the elevators draw from?

## Elevators

9. **Load Elevator** — does it need the doors open first, or does it open them?
   Is this also affected by Automatic Doors?

10. **Capacity per elevator?** Is a full elevator worth more than a partial one,
    or is it purely per-guest?

11. **Dispatch** — what exactly must be true? Loaded at all / loaded full / doors
    closed / track clear? How long is one full ride cycle before that elevator is
    usable again?

12. **The two greens.** ⚠️ *The one I most need right.* In your elevator
    screenshot, `Elevator 1 Enabled` and `Dispatch Elevator` are both green but
    look like different shades. What does each mean — is one "this toggle is on"
    and the other "this action is available right now"? Do any **other** buttons
    use the brighter action-green?

## Track

13. What is the track, and what makes **Track Ready** flip to red? One elevator
    occupying it, or something else? Is it shared across all three elevators, or
    is that indicator per-elevator?

14. Roughly how long does it stay blocked?

## Scoring and time

15. **What earns points?** Per guest served? Bonuses for full elevators, fast
    turnaround, keeping queues short? Any penalties?

16. The timed game is 12 virtual hours — **10:00 to 22:00**? How many **real
    seconds** is one virtual minute? (I need this to size timeouts sensibly.)

17. Anything that **ends the run early**, or is it always the full 12 hours?

## Failure modes

18. Can you **jam** the attraction into a stuck state? How would you recognise it
    on the panel, and how do you recover?

19. What do the **Enabled/Disabled** toggles on elevators and TV rooms do — take a
    unit out of service? Is there ever a reason to disable one deliberately?

20. Anything that **looks** like it should work but doesn't? Any button that's a
    trap, or that punishes you for clicking it at the wrong moment?

## Free-form

21. Anything else you already know about playing this well. Even a vague
    "I think you want to stagger the elevators" is useful — it tells me which
    timing relationships to make sure the trace captures.
