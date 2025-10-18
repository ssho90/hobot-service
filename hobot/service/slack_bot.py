import os
from dotenv import load_dotenv
import time

load_dotenv(override = True)

token = os.environ['SL_TOKEN']

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

client = WebClient(token)

def post_message(bot_message, max_retries=3, retry_delay=5, channel='#upbit-alarm'):
    """
    Sends a message to a Slack channel with retry logic.

    Args:
        bot_message (str): The message to send.
        max_retries (int): The maximum number of retry attempts.
        retry_delay (int): The delay in seconds between retries.

    Returns:
        bool: True if the message was successfully sent, False otherwise.
    """
    for attempt in range(max_retries):
        try:
            response = client.chat_postMessage(channel=channel, text=bot_message)
            if response['ok']:
                return True  # Message sent successfully
            else:
                print(f"Slack API error: {response}")
                # Log the error for further investigation
                return False

        except SlackApiError as e:
            print(f"Slack API error: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"Max retries reached. Failed to send message: {bot_message}")
                return False  # Indicate failure after max retries

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"Max retries reached. Failed to send message: {bot_message}")
                return False

    return False  # Indicate failure if loop completes without success