"""Your strategy goes here.

Everything below the setup block is a skeleton. The classes deliberately contain
no decisions: every property is one thing on screen, so every branch you write
here maps to one instruction a person can follow.

    python main.py

Read `game.describe()` or the JSONL trace in logs/ to see what the bot saw.
"""

from __future__ import annotations

from tot import Game, Screen

# The Simulation Page only offers the Unlimited game. Point this at the TM Arcade
# URL when you want the timed, scored 12-hour run.
URL = None  # None uses tot.DEFAULT_URL


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

    with game:
        game.refresh()
        if game.screen is not Screen.PLAYING:
            print("Not on the playing field. Choose a game mode, then re-run.")
            return

        print(f"clock {game.clock}   score {game.score}")
        for line in game.describe():
            print(" ", line)

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
