"""Your strategy goes here.

Everything below the setup block is a skeleton. The classes deliberately contain
no decisions: every property is one thing on screen, so every branch you write
here maps to one instruction a person can follow.

    python main.py

Read `game.describe()` or the JSONL trace in logs/ to see what the bot saw.
"""

from __future__ import annotations
import time

from tot import Game, Screen

# The Simulation Page only offers the Unlimited game. Point this at the TM Arcade
# URL when you want the timed, scored 12-hour run.
URL = None  # None uses tot.DEFAULT_URL

# game.tv_room1 / game.tv_room2   (TV Room 1 & 2)
#   Read:
#     waiting, loaded                                   # counters
#     load_button, unload_button, entrance, exit,
#     enable_button, preshow                             # raw states
#     can_load, is_loading, unload_ready, is_unloading,
#     entrance_is_closed / _moving / _open,
#     exit_is_closed / _moving / _open,
#     enabled, preshow_ready, preshow_running             # booleans
#   Click:
#     load(), unload(), start_preshow(), toggle_enabled()

# game.elevator1 / elevator2 / elevator3
#   Read:
#     waiting, loaded
#     enable_button, doors, load_button, dispatch_button  # raw states
#     enabled, doors_are_closed / _moving / _open,
#     can_load, is_loading, can_dispatch, is_dispatched    # booleans
#   Click:
#     load(), dispatch(), toggle_enabled(), toggle_doors()

# game.track
#   Read only (no buttons — shared shaft status):
#     state, is_ready, is_locked

# game.control   (global RideControl panel)
#   Read:
#     front_waiting, back_waiting, visitor_counter         # counters
#     attraction, attraction_is_active, attraction_is_closed
#     automatic_doors / automatic_doors_on
#     daytime / daytime_on
#     show_fullscreen
#     ride_sfx / ride_sfx_on
#     tv_room_sound / tv_room_sound_on
#     bgm / bgm_on
#   Click:
#     toggle_attraction(), toggle_automatic_doors(), toggle_daytime(),
#     toggle_show_fullscreen(), toggle_ride_sfx(),
#     toggle_tv_room_sound(), toggle_bgm()

# game   (top level)
#   Read:
#     clock, score, screen
#   Actions:
#     refresh()                       # take one screenshot/frame
#     wait_until(predicate, timeout=30.0, poll=0.1)
#     describe() / snapshot()         # debugging dumps

# --------------------------------------------------------------------------
# All clickable buttons, tallied:
#   TV rooms   (x2): load, unload, start_preshow, toggle_enabled     -> 8 buttons
#   Elevators  (x3): load, dispatch, toggle_enabled, toggle_doors    -> 12 buttons
#   Global     (x1): toggle_attraction, toggle_automatic_doors,
#                     toggle_daytime, toggle_show_fullscreen,
#                     toggle_ride_sfx, toggle_tv_room_sound,
#                     toggle_bgm                                      -> 7 buttons
#
# Track and all counters (waiting/loaded/score/clock/visitor counts)
# are read-only — not clickable.


def main() -> None:
    game = Game.launch(
        url=URL or __import__("tot").DEFAULT_URL,
        headless=False,
        trace="logs/run.jsonl",
        # "raise" stops the run on any colour we have not seen before. Switch to
        # "unknown" only once you trust the calibration.
        on_unknown="raise",
        # 0.0 lets the bot play as fast as it can. Set a floor (say 0.4) to find
        # out what the same strategy scores at human speed.
        min_click_interval=0.0,
    )

    time.sleep(5)

    with game:
        game.refresh()
        if game.screen is not Screen.PLAYING:
            print("Not on the playing field. Choose a game mode, then re-run.")
            return

        print(f"clock {game.clock}   score {game.score}")
        for line in game.describe():
            print(" ", line)

        if not game.control.attraction_is_active:
            game.control.toggle_attraction()
            game.wait_until(lambda: game.control.attraction_is_active, timeout=20, poll=0.5)

        game.tv_room1.toggle_enabled()

        while (game.tv_room1.waiting < 21):
            game.refresh()

        game.tv_room1.load()

        time.sleep(10)

        # ------------------------------------------------------------------
        # Strategy starts here.
        #
        # A tick looks like:
        #
        #     game.refresh()                     # one screenshot, frozen
        #     if game.tv_room1.preshow_ready:    # Start Preshow is orange
        #         game.tv_room1.start_preshow()
        #
        # Useful shapes:
        #
        #     for lift in game.elevators.values():
        #         if lift.can_dispatch and not game.track.is_locked:
        #             lift.dispatch()
        #
        #     game.wait_until(lambda: game.tv_room1.unload_ready, timeout=60)
        #
        # Reference for what is readable:
        #
        #   tv_room1 / tv_room2   waiting loaded
        #                         load_button unload_button entrance exit
        #                         enable_button preshow
        #                         can_load is_loading unload_ready is_unloading
        #                         entrance_is_closed/_moving/_open
        #                         exit_is_closed/_moving/_open
        #                         enabled preshow_ready preshow_running
        #                         load() unload() start_preshow() toggle_enabled()
        #
        #   elevator1/2/3         waiting loaded
        #                         enable_button doors load_button dispatch_button
        #                         enabled doors_are_closed/_moving/_open
        #                         can_load is_loading can_dispatch is_dispatched
        #                         load() dispatch() toggle_enabled() toggle_doors()
        #
        #   control               front_waiting back_waiting visitor_counter
        #                         attraction attraction_is_active/_closed
        #                         automatic_doors daytime show_fullscreen
        #                         ride_sfx tv_room_sound bgm  (+ *_on aliases)
        #                         toggle_attraction() toggle_*()
        #
        #   track                 state is_ready is_locked
        #   game                  clock score screen refresh() wait_until()
        # ------------------------------------------------------------------


if __name__ == "__main__":
    main()
