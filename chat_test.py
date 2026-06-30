import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the AI response function
from ai_engine.gemini_engine import get_ai_response


def main():
    print("=" * 60)
    print("        CloudLens AI - Ollama Interactive Chat Test")
    print("=" * 60)
    print("This tool lets you chat directly with the local Ollama AI engine.")
    print("Type your question and press Enter.")
    print("Type 'exit' or 'quit' to end the session.")
    print("=" * 60)

    while True:
        try:
            user_question = input("\nYou: ").strip()

            # Exit condition
            if user_question.lower() in ("exit", "quit"):
                print("\nGoodbye! Thanks for testing the Ollama AI engine.")
                break

            # Ignore empty input
            if not user_question:
                print("Please enter a question.")
                continue

            print("\nThinking...\n")

            try:
                response = get_ai_response(user_question, mode="ollama")

                if isinstance(response, str) and response.startswith("Ollama error:"):
                    print(response)
                    print("Check that Ollama is running: 'ollama run llama3.2:1b' in another terminal.")
                    continue

                print("----- CloudLens AI (Ollama) says -----")
                print(response)

            except Exception as e:
                print(f"Error while contacting Ollama: {e}")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Goodbye!")
            break


if __name__ == "__main__":
    main()