
"""
main.py - Entry point for the Rock Paper Scissors game
 
Connects the camera model (model.py) with the game logic (game.py):
  1. Get the user's move (from the camera, placeholder for now)
  2. Play one round against the computer
  3. Show the result and score
  4. Ask the user whether to play again
"""
 
import game
import model   # TODO: uncomment once the camera model is ready
 
 
def get_user_move():
    """
    [PLACEHOLDER] Get the user's move.
 
    TODO: Replace with the camera model once it's ready, e.g.:
        return model.detect_gesture()   # returns "rock" / "paper" / "scissors", or None if detection fails
 
    For now, read from the keyboard so the game can be tested.
    """
    return input("Enter your move (rock / paper / scissors): ").strip().lower()
 
 
def ask_play_again():
    """Ask the user whether to play another round. Returns True or False."""
    while True:
        answer = input("Play again? (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")
 
 
def print_result(user_move, computer_move, result):
    """Print the moves and who won this round."""
    print(f"You played: {user_move}  |  Computer played: {computer_move}")
    if result == "user":
        print("You win!")
    elif result == "computer":
        print("Computer wins!")
    else:
        print("It's a tie!")
 
 
def print_score(score):
    """Print the current score."""
    print(f"Score - You: {score['user']}  Computer: {score['computer']}  Ties: {score['tie']}\n")
 
 
def main():
    score = {"user": 0, "computer": 0, "tie": 0}
    print("=== Rock Paper Scissors ===\n")
 
    playing = True
    while playing:
        # 1. Get the user's move (placeholder until the camera model is ready)
        user_move = get_user_move()
 
        # If the move is not valid (e.g. camera could not detect a gesture), redo this round
        if not game.is_valid_move(user_move):
            print("No valid gesture detected, please try again.\n")
            continue
 
        # 2. Play one round: computer picks a move, then decide the winner
        computer_move, result = game.play_round(user_move)
 
        # 3. Update and show the result and score
        score[result] += 1
        print_result(user_move, computer_move, result)
        print_score(score)
 
        # 4. Ask whether to keep playing
        playing = ask_play_again()
        print()
 
    print("Thanks for playing! Final score:")
    print_score(score)
 
 
if __name__ == "__main__":
    main()
