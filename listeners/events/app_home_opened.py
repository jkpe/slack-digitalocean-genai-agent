from logging import Logger
from ai.providers import get_available_providers
from slack_sdk import WebClient
from state_store.get_redis_user_state import get_redis_user_state
from state_store.set_redis_user_state import set_redis_user_state
import sys
import os

"""
Callback for handling the 'app_home_opened' event. It checks if the event is for the 'home' tab,
generates a list of model options for a dropdown menu, retrieves the user's state to set the initial option,
and publishes a view to the user's home tab in Slack.
"""


def app_home_opened_callback(event: dict, logger: Logger, client: WebClient):
    if event["tab"] != "home":
        return

    user_id = event["user"]
    print(f"🏠 App Home opened by user: {user_id}")

    # create a list of options for the dropdown menu each containing the model name and provider
    options = [
        {
            "text": {"type": "plain_text", "text": f"{model_info['name']} ({model_info['provider']})", "emoji": True},
            "value": f"{model_name} {model_info['provider'].lower()}",
        }
        for model_name, model_info in get_available_providers().items()
    ]

    provider = None
    model = None
    initial_option = None
    
    # Check if Redis is available
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            # retrieve user's state to determine if they already have a selected model
            provider, model = get_redis_user_state(user_id, True, redis_url)
        except Exception as e:
            print(f"⚠️ Failed to get user state from Redis: {e}")
            # Fall through to default handling

    if provider and model:
        print(f"📋 Retrieved user state from Redis - User: {user_id}, Provider: {provider}, Model: {model}")
        # set the initial option to the user's previously selected model
        initial_option = list(filter(lambda x: x["value"].startswith(model), options))
        if not initial_option:
            print(f"⚠️ No matching option found for model '{model}', using default")
    else:
        print(f"ℹ️ No provider selection found for user: {user_id}")
        # Check if GENAI_API_URL is set and genai-agent is available
        genai_api_url = os.environ.get("GENAI_API_URL")
        if genai_api_url and any(opt["value"].startswith("genai-agent") for opt in options):
            print(f"🔄 Using genai-agent as default model for user: {user_id}")
            initial_option = list(filter(lambda x: x["value"].startswith("genai-agent"), options))
            if initial_option and redis_url:
                # Save the default selection to Redis (only if Redis is available)
                try:
                    set_redis_user_state(user_id, "genai", "genai-agent", redis_url)
                    print(f"✅ Saved default GenAI selection to Redis for user: {user_id}")
                except Exception as e:
                    print(f"❌ Error saving default GenAI selection: {e}", file=sys.stderr)
                    logger.error(f"Error saving default GenAI selection: {e}")
    
    # If no option was selected, add a default "Select a provider" option
    if not initial_option:
        # Show a message that GenAI will be used as fallback if available
        genai_api_url = os.environ.get("GENAI_API_URL")
        if genai_api_url and any(opt["value"].startswith("genai-agent") for opt in options):
            options.append(
                {
                    "text": {"type": "plain_text", "text": "Select a provider (GenAI used as fallback)", "emoji": True},
                    "value": "null",
                }
            )
        else:
            options.append(
                {
                    "text": {"type": "plain_text", "text": "Select a provider", "emoji": True},
                    "value": "null",
                }
            )

    try:
        client.views_publish(
            user_id=user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "Welcome to Sailor Home Page!", "emoji": True},
                    },
                    {"type": "divider"},
                    {
                        "type": "rich_text",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "Pick an option", "style": {"bold": True}}],
                            }
                        ],
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "static_select",
                                "initial_option": initial_option[0] if initial_option else options[-1],
                                "options": options,
                                "action_id": "pick_a_provider",
                            }
                        ],
                    },
                ],
            },
        )
        print(f"✅ Successfully published home view for user: {user_id}")
    except Exception as e:
        print(f"❌ Error publishing home view: {e}", file=sys.stderr)
        logger.error(e)
