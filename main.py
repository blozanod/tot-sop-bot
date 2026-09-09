"""Your strategy goes here.

    python main.py

The bot opens the page and then waits. **You** load the game and pick the mode —
it will not touch anything. The moment the RideControl panel appears on screen the
game has begun, ``wait_for_panel()`` returns, and the loop below starts.

Everything below the setup block is a skeleton. The classes deliberately contain
no decisions: every property is one thing on screen, so every branch you write
here maps to one instruction a person could follow.
"""

from __future__ import annotations

from tot import DEFAULT_URL, Game, RuffleCrashed

# The Simulation Page only offers the Unlimited game. Point this at the TM Arcade
# URL when you want the timed, scored run.
URL = DEFAULT_URL

# --------------------------------------------------------------------------
# What is readable, in full.
#
# game.tv_room1 / game.tv_room2
#   States:  load_button unload_button entrance exit enable_button preshow
#   Booleans: can_load is_loading unload_ready is_unloading
#             entrance_is_closed/_moving/_open  exit_is_closed/_moving/_open
#             enabled preshow_ready preshow_running
#   Counters: waiting loaded                       -> Count.ZERO / FULL / OTHER
#             waiting_is_zero waiting_is_full loaded_is_zero loaded_is_full
#   Clicks:   load() unload() start_preshow() toggle_enabled()
#
# game.elevator1 / elevator2 / elevator3
#   States:   enable_button doors load_button dispatch_button
#   Booleans: enabled doors_are_closed/_moving/_open
#             can_load is_loading can_dispatch is_dispatched
#   Counters: waiting loaded (+ the four booleans, as above)
#   Clicks:   load() dispatch() toggle_enabled() toggle_doors()
#
# game.track       state is_ready is_locked           (read-only)
# game.control     attraction attraction_is_active/_closed
#                  front_waiting back_waiting front_queue_is_full back_queue_is_full
#                  automatic_doors daytime ride_sfx tv_room_sound bgm
#                  toggle_attraction() toggle_automatic_doors() toggle_daytime()
#                  toggle_show_fullscreen() toggle_ride_sfx()
#                  toggle_tv_room_sound() toggle_bgm()
# game             refresh() wait_until(pred, timeout) describe() panel_visible
#
# A counter only ever says ZERO, FULL (21) or OTHER. Those are the two numbers a
# decision turns on; every other value means "wait", and the bot does not spend a
# frame working out which one it is.
#
# All 27 clickable buttons: 8 across the TV rooms, 12 across the elevators,
# 7 on RideControl. Track and every counter are read-only.
# --------------------------------------------------------------------------


def play(game: Game) -> None:
    """One pass of your strategy. Called in a loop, once per frame.

    ``game`` has already been refreshed, so every property below describes the
    same instant. Do not refresh in here.
    """
    # Open the attraction, once.
    if not game.control.attraction_is_active:
        game.control.toggle_attraction()
        return

    # ------------------------------------------------------------------
    # Strategy starts here. A rule is one observable and one click:
    #
    #     for room in game.tv_rooms.values():
    #         if room.preshow_ready:            # Start Preshow has turned orange
    #             room.start_preshow()
    #         elif room.unload_ready:           # Unload has turned orange
    #             room.unload()
    #         elif room.can_load and room.waiting_is_full:
    #             room.load()                   # a full 21 are queued
    #
    #     for lift in game.elevators.values():
    #         if lift.can_dispatch and not game.track.is_locked:
    #             lift.dispatch()
    #         elif lift.can_load and not lift.waiting_is_zero:
    #             lift.load()
    # ------------------------------------------------------------------


def main() -> None:
    game = Game.launch(
        url=URL,
        headless=False,
        # "raise" stops the run on a fill we have not seen before. There is no
        # "guess" mode on purpose: a misread colour is a wrong decision.
        on_unknown="raise",
        # 0.0 lets the bot play as fast as it can. Set a floor (say 0.4) to find
        # out what the same strategy scores at human speed.
        min_click_interval=0.0,
    )

    with game:
        print("Load the game and pick your mode. I start when I can see the panel.")
        if not game.wait_for_panel(timeout=600):
            print("No RideControl panel after 10 minutes — giving up.")
            print(game.backend.describe_page())
            return

        print(f"Panel found ({game.layout.region.w}x{game.layout.region.h} crop). Playing.")
        try:
            while game.refresh():
                play(game)
        except RuffleCrashed as exc:
            print(f"\n{exc}\nReload the page and run again.")
        except KeyboardInterrupt:
            pass

        if not game.panel_visible:
            print("The panel went away — the game is over, or the emulator dropped it.")


if __name__ == "__main__":
    main()
