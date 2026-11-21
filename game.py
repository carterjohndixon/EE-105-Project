"""
game.py - Rock Paper Scissors game logic
 
Responsibilities:
  1. Generate the computer's move at random
  2. Decide who wins between the user and the computer
 
The user's move will eventually come from the camera module (in progress by a teammate).
For now, get_user_move() is a placeholder; once the camera module is ready,
only that one function needs to change.
"""
 
import random
 
# Moves are represented by these three strings.
# The camera module should return the same strings.
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
 
 
def get_user_move():
    """
    [PLACEHOLDER] Get the user's move.
 
    TODO: Replace with the camera module once it's ready, e.g.:
        from camera import detect_gesture
        return detect_gesture()   # returns "rock" / "paper" / "scissors", or None if detection fails
 
    For now, read from the keyboard so the game logic can be tested.
    """
    move = input("Enter your move (rock / paper / scissors, or q to quit): ").strip().lower()
    if move == "q":
        return "quit"
    return move
 
 
def get_computer_move():
    """Return a random move for the computer."""
    return random.choice(CHOICES)
 
 
def determine_winner(user_move, computer_move):
    """
    Decide the winner of one round.
    Returns: "user" / "computer" / "tie"
    """
    if user_move not in CHOICES:
        raise ValueError(f"Invalid user move: {user_move}")
    if computer_move not in CHOICES:
        raise ValueError(f"Invalid computer move: {computer_move}")
 
    if user_move == computer_move:
        return "tie"
    if BEATS[user_move] == computer_move:
        return "user"
    return "computer"
 
 
def play_round(user_move):
    """
    Play one round: takes the user's move, returns (computer_move, result).
    The camera module or a main program can call this directly.
    """
    computer_move = get_computer_move()
    result = determine_winner(user_move, computer_move)
    return computer_move, result
 
 
def main():
    score = {"user": 0, "computer": 0, "tie": 0}
    print("=== Rock Paper Scissors ===")
 
    while True:
        user_move = get_user_move()
 
        if user_move == "quit":
            break
        if user_move not in CHOICES:
            # Camera failed to detect a gesture or input was invalid: try again
            print("No valid gesture detected, please try again.\n")
            continue
 
        computer_move, result = play_round(user_move)
        score[result] += 1
 
        print(f"You played: {user_move}  |  Computer played: {computer_move}")
        if result == "user":
            print("You win!")
        elif result == "computer":
            print("Computer wins!")
        else:
            print("It's a tie!")
        print(f"Score - You: {score['user']}  Computer: {score['computer']}  Ties: {score['tie']}\n")
 
    print("Game over. Final score:", score)
 
 
if __name__ == "__main__":
    main()
