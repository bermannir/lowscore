
"""
Module: main
Purpose: Entry point for LOWSCORE.
Dependencies: lowscore.core.game
Used by: Users running the game from the command line.
"""

from core.game import Game


def main() -> None:
    """Create and run the game."""
    game = Game()
    game.run()


if __name__ == "__main__":
    main()

