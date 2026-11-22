"""
game.py - Rock Paper Scissors game logic

Responsibilities:
  1. Generate the computer's move at random
  2. Decide who wins between the user and the computer

The user's move is passed in as a parameter (user_move). It will come from
the camera model (model.py), and main.py connects the two.
"""

import random

# Moves are represented by these three strings.
# The camera model should return the same strings.
ROCK = "rock"
PAPER = "paper"
SCISSORS = "scissors"
CHOICES = [ROCK, PAPER, SCISSORS]

# Each key beats its value: rock beats scissors, scissors beats paper, paper beats rock
BEATS = {
    ROCK: SCISSORS,
    SCISSORS: PAPER,
    PAPER: ROCK,
}


def is_valid_move(move):
    """Return True if move is one of "rock" / "paper" / "scissors"."""
    return move in CHOICES


def get_computer_move():
    """Return a random move for the computer."""
    return random.choice(CHOICES)


def determine_winner(user_move, computer_move):
    """
    Decide the winner of one round.
    Returns: "user" / "computer" / "tie"
    """
    if not is_valid_move(user_move):
        raise ValueError(f"Invalid user move: {user_move}")
    if not is_valid_move(computer_move):
        raise ValueError(f"Invalid computer move: {computer_move}")

    if user_move == computer_move:
        return "tie"
    if BEATS[user_move] == computer_move:
        return "user"
    return "computer"


def play_round(user_move):
    """
    Play one round.

    user_move: the user's move from the camera model (placeholder until model.py is ready)
    Returns: (computer_move, result), where result is "user" / "computer" / "tie"
    """
    computer_move = get_computer_move()
    result = determine_winner(user_move, computer_move)
    return computer_move, result
