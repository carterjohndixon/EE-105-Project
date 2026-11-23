
"""
main.py - Entry point for the Rock Paper Scissors game
 
Connects the camera model (model.py) with the game logic (game.py):
  1. Get the user's move (from the camera, placeholder for now)
  2. Play one round against the computer
  3. Show the result and score
  4. Ask the user whether to play again
"""
 
import game
# import model   # TODO: uncomment once the camera model is ready
import model
 
def get_user_move():
    """
    Get the user's move from the camera model.
    """
    # return input("Enter your move (rock / paper / scissors): ").strip().lower() # Place holder for no camera
    key = input ("Show your gesture to the camera and press Enter (or type q + Enter to quit): ")
    if key.strip().lower() == "q":
        return "quit"
    return model.detect_gesture()  # returns "rock" / "paper" / "scissors", or None if detection fails
 
 
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
 
 
def print_statistics(score, title="Statistics"):
    """Print the running statistics: wins for each side, ties, rounds played and win rate."""
    rounds = score["user"] + score["computer"] + score["tie"]
    win_rate = (score["user"] / rounds * 100) if rounds else 0.0

    print(f"--- {title} ---")
    print(f"You: {score['user']} | Computer: {score['computer']} | Ties: {score['tie']}")
    print(f"Rounds played: {rounds} | Your win rate: {win_rate:.1f}%\n")
 
 
def main():
    score = {"user": 0, "computer": 0, "tie": 0}
    print("=== Rock Paper Scissors ===\n")

    print("Loading the model and connecting to the camera...")

    try:
        model.load_best()  # Load the best model (weights) for the camera
        model.open_camera()  # Connect to the camera (raises RuntimeError if not found)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"Can't start the game: {e}")
        return

    playing = True
    try:
        while playing:
            # 1. Get the user's move from the camera
            user_move = get_user_move()
            if user_move == "quit":
                break  # Exit the game if the user wants to quit
    
            # If the move is not valid (e.g. camera could not detect a gesture), redo this round
            if not game.is_valid_move(user_move):
                print("No valid gesture detected, please try again.\n")
                continue
    
            # 2. Play one round: computer picks a move, then decide the winner
            computer_move, result = game.play_round(user_move)
    
            # 3. Update and show the result and statistics
            score[result] += 1
            print_result(user_move, computer_move, result)
            print_statistics(score)
    
            # 4. Ask whether to keep playing
            playing = ask_play_again()
            print()
    
        print("Thanks for playing!")
        print_statistics(score, title="Final Statistics")
    except KeyboardInterrupt:
        print("\n Game stopped.")
    finally:
        model.close_camera()  # Close the camera when the game ends


if __name__ == "__main__":
    main()