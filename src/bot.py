import logging
import os
import re
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv
from flask import Flask, request

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALERT_CHAT_ID = os.getenv("ALERT_CHAT_ID")
DEBUG_MODE = int(os.getenv("DEBUG_MODE", "0"))
PROJECT_TELEGRAM_MENTIONS = os.getenv("PROJECT_TELEGRAM_MENTIONS", "")

# Configure logging
if DEBUG_MODE:
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logging.debug("Debug mode enabled")
else:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

app = Flask(__name__)


def escape_markdown_v2(text):
    """Escapes characters for Telegram MarkdownV2."""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in escape_chars else char for char in str(text))


def normalize_project_key(value):
    # Normalize separators so `my-project`, `my_project`, and `my project` map alike.
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower())
    return " ".join(normalized.split())


def parse_project_telegram_mentions(raw_value):
    """Parses `project:user1,user2;project2:user3` into a normalized mapping."""
    mapping = {}
    if not raw_value:
        return mapping

    for chunk in raw_value.split(";"):
        entry = chunk.strip()
        if not entry:
            continue

        if ":" not in entry:
            logging.warning(
                "Skipping malformed PROJECT_TELEGRAM_MENTIONS entry (missing ':'): %s",
                entry,
            )
            continue

        project_name, mentions_raw = entry.split(":", 1)
        project_key = normalize_project_key(project_name)
        if not project_key:
            continue

        mentions = [item.strip() for item in mentions_raw.split(",") if item.strip()]
        if not mentions:
            continue

        project_targets = mapping.setdefault(project_key, [])
        for mention in mentions:
            if mention not in project_targets:
                project_targets.append(mention)

    return mapping


def format_telegram_mention(target):
    target = str(target).strip()
    if not target:
        return ""

    if target.startswith("@"):
        return escape_markdown_v2(target)

    numeric_id = ""
    if target.lower().startswith("id:"):
        numeric_id = target.split(":", 1)[1].strip()
    elif target.isdigit():
        numeric_id = target

    if numeric_id and numeric_id.isdigit():
        label = escape_markdown_v2(f"user_{numeric_id}")
        return f"[{label}](tg://user?id={numeric_id})"

    return escape_markdown_v2(target)


def _best_title_project_key(title):
    normalized_title = normalize_project_key(title)
    if not normalized_title:
        return ""

    padded_title = f" {normalized_title} "
    phrase_matches = [
        key for key in PROJECT_MENTION_MAP if key and f" {key} " in padded_title
    ]

    if len(phrase_matches) == 1:
        return phrase_matches[0]
    if len(phrase_matches) > 1:
        longest = max(len(key) for key in phrase_matches)
        winners = [key for key in phrase_matches if len(key) == longest]
        if len(winners) == 1:
            return winners[0]
        return ""

    title_tokens = normalized_title.split()
    if not title_tokens:
        return ""

    best_key = ""
    best_score = 0.0
    tied = False

    for key in PROJECT_MENTION_MAP:
        key_tokens = key.split()
        if not key_tokens:
            continue

        fuzzy_hits = 0
        for key_token in key_tokens:
            token_score = max(
                (SequenceMatcher(None, key_token, title_token).ratio() for title_token in title_tokens),
                default=0,
            )
            if token_score >= 0.86:
                fuzzy_hits += 1

        score = fuzzy_hits / len(key_tokens)
        if score > best_score:
            best_key = key
            best_score = score
            tied = False
        elif score == best_score and score > 0:
            tied = True

    if tied or best_score < 0.8:
        return ""

    return best_key


def resolve_mentions_for_alert(project_name, title, status_text):
    # Keep mention noise low: only ping assignees on service state changes.
    if status_text not in {"UP", "DOWN"}:
        return ""

    project_key = normalize_project_key(project_name)
    target_key = ""

    if project_key and project_key in PROJECT_MENTION_MAP:
        target_key = project_key
    else:
        target_key = _best_title_project_key(title)

    targets = PROJECT_MENTION_MAP.get(target_key, [])
    formatted_mentions = [format_telegram_mention(target) for target in targets]
    formatted_mentions = [item for item in formatted_mentions if item]

    if formatted_mentions:
        logging.debug(
            "Resolved mentions for alert using key '%s' (project='%s', title='%s')",
            target_key,
            project_name,
            title,
        )

    return " ".join(formatted_mentions)


PROJECT_MENTION_MAP = parse_project_telegram_mentions(PROJECT_TELEGRAM_MENTIONS)
if PROJECT_MENTION_MAP:
    logging.info(
        "Loaded project mention mapping for %d project(s)", len(PROJECT_MENTION_MAP)
    )


@app.route("/", methods=["POST", "GET"])
def glitchtip_webhook():
    if request.method == "GET":
        logging.debug("Received GET request at root '/'")
        return "OK", 200

    logging.debug("Received POST request at root '/'")
    payload = request.json

    logging.debug(f"Full payload received: {payload}")

    if payload and payload.get("alias") == "GlitchTip":
        try:
            attachments = payload.get("attachments", [])
            messages = []

            for att in attachments:
                title = att.get("title", "No title")
                link = att.get("title_link", "")
                text = att.get("text", "")
                color = att.get("color", "")
                fields = att.get("fields", [])

                project = ""
                environment = ""
                release = ""
                server_name = ""
                url = ""
                expected_status = ""
                timeout = ""

                if fields:
                    for field in fields:
                        field_title = field.get("title")
                        field_value = field.get("value")

                        if field_title == "Project":
                            project = field_value
                        elif field_title == "Environment":
                            environment = field_value
                        elif field_title == "Release":
                            release = field_value
                        elif field_title == "Server Name":
                            server_name = field_value
                        elif field_title == "URL":
                            url = field_value
                        elif field_title == "Expected status":
                            expected_status = field_value
                        elif field_title == "Timeout":
                            timeout = field_value

                status_emoji = ""
                status_text = ""
                if color:
                    if color.lower() in ["#ff0000", "red", "danger"]:
                        status_emoji = "🔴"
                        status_text = "DOWN"
                    elif color.lower() in ["#00ff00", "green", "good"]:
                        status_emoji = "🟢"
                        status_text = "UP"
                    elif color.lower() in ["#ffff00", "yellow", "warning"]:
                        status_emoji = "🟡"
                        status_text = "WARNING"
                    else:
                        status_emoji = "⚪"
                        status_text = "UNKNOWN"
                else:
                    text_lower = text.lower() if text else ""
                    if any(keyword in text_lower for keyword in ["back up", "is up", "recovered", "resolved"]):
                        status_emoji = "🟢"
                        status_text = "UP"
                    elif any(keyword in text_lower for keyword in ["down", "failed", "error", "unavailable"]):
                        status_emoji = "🔴"
                        status_text = "DOWN"

                mentions = resolve_mentions_for_alert(project, title, status_text)

                title = escape_markdown_v2(title)
                text = escape_markdown_v2(text)
                project = escape_markdown_v2(project)
                environment = escape_markdown_v2(environment)
                release = escape_markdown_v2(release)
                server_name = escape_markdown_v2(server_name)
                url = escape_markdown_v2(url)
                expected_status = escape_markdown_v2(expected_status)
                timeout = escape_markdown_v2(timeout)
                link = escape_markdown_v2(link)

                issue_message = ""

                if status_text:
                    issue_message += f"{status_emoji} *Status*: {escape_markdown_v2(status_text)}\n\n"

                if mentions:
                    issue_message += f"*Ping*: {mentions}\n"

                issue_message += f"*Title*: {title}\n"

                if text:
                    issue_message += f"*Description*: {text}\n"

                if url:
                    issue_message += f"*Monitored URL*: {url}\n"

                if project:
                    issue_message += f"*Project*: {project}\n"
                if environment:
                    issue_message += f"*Environment*: {environment}\n"
                if release:
                    issue_message += f"*Release*: {release}\n"
                if server_name:
                    issue_message += f"*Server Name*: {server_name}\n"
                if expected_status:
                    issue_message += f"*Expected Status*: {expected_status}\n"
                if timeout:
                    issue_message += f"*Timeout*: {timeout}\n"

                issue_message += f"*Link*: {link}"

                messages.append(issue_message)

            if messages:
                # Combine all formatted issues into a single message
                separator = "\n\n*New GlitchTip Event*\n\n"
                combined_message = "*New GlitchTip Event*\n\n" + separator.join(
                    messages
                )
                send_telegram_message(
                    ALERT_CHAT_ID, combined_message, parse_mode="MarkdownV2"
                )
        except Exception as e:
            logging.exception(f"Error processing GlitchTip payload: {e}")
    else:
        logging.warning("Received POST with empty or invalid payload")

    return "OK", 200


def send_telegram_message(chat_id, text, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode

    logging.debug(f"Sending message to Telegram: {data}")
    try:
        r = requests.post(url, json=data, timeout=60)
        logging.debug(f"Telegram response: {r.status_code} {r.text}")
    except Exception as e:
        logging.exception(f"Error sending message to Telegram: {e}")


if __name__ == "__main__":
    port = 8844
    logging.info(f"Starting server on port {port} (debug={DEBUG_MODE})")
    app.run(host="0.0.0.0", port=port)
