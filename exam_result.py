import json
import logging
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Replace with your actual bot token obtained from BotFather
TELEGRAM_BOT_TOKEN = "8207519709:AAFnE_HI4vGxB26Jd0Aq9HMBHWwBdZ3qOtU"
JSON_FILE_PATH = "exam_result.json"

# Global variable to store exam data
EXAM_DATA = None

def load_exam_data(file_path):
    """Loads the exam data from the JSON file."""
    global EXAM_DATA
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            EXAM_DATA = json.load(f)
        logger.info(f"Successfully loaded data from {file_path}")
    except FileNotFoundError:
        logger.error(f"Error: JSON file not found at {file_path}")
        EXAM_DATA = {"result": []} # Initialize with empty data to prevent errors
    except json.JSONDecodeError:
        logger.error(f"Error: Could not decode JSON from {file_path}. Check file format.")
        EXAM_DATA = {"result": []}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading JSON: {e}")
        EXAM_DATA = {"result": []}

def search_exam_results(query: str):
    """
    Searches the loaded exam data for results matching the query.
    The search is case-insensitive and looks for matches in RollNo, ExamLocation, and Division.
    """
    if EXAM_DATA is None or not EXAM_DATA.get("result"):
        return []

    query_lower = query.lower()
    found_results = []

    for year_data in EXAM_DATA["result"]:
        division = year_data.get("division", "")
        # Check if the division itself matches the query
        if query_lower in division.lower():
            # If division matches, add all departments from this division
            for dept in year_data.get("examdepartment", []):
                found_results.append({
                    "year": year_data.get("year", "N/A"),
                    "division": division,
                    "RollNo": dept.get("RollNo", "N/A"),
                    "ExamLocation": dept.get("ExamLocation", "N/A"),
                    "Download": dept.get("Download", "N/A")
                })
            continue # Move to the next year_data after adding all departments

        for department in year_data.get("examdepartment", []):
            roll_no = department.get("RollNo", "")
            exam_location = department.get("ExamLocation", "")

            if query_lower in roll_no.lower() or query_lower in exam_location.lower():
                found_results.append({
                    "year": year_data.get("year", "N/A"),
                    "division": division,
                    "RollNo": roll_no,
                    "ExamLocation": exam_location,
                    "Download": department.get("Download", "N/A")
                })
    return found_results

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your Exam Result Bot.\n\n"
        "Send me a Roll Number, Exam Location, or Division name to find results. "
        "For example, you can send 'တိုက်ကြီး' or '(ဆဘ)' or 'ရန်ကုန်တိုင်းဒေသကြီး'.",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    await update.message.reply_text(
        "Send me a Roll Number, Exam Location, or Division name to find results. "
        "I will search for matches and provide download links if available."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text messages and searches for exam results."""
    user_query = update.message.text
    logger.info(f"User {update.effective_user.id} ({update.effective_user.first_name}) searched for: {user_query}")

    if EXAM_DATA is None or not EXAM_DATA.get("result"):
        await update.message.reply_text(
            "I'm sorry, I couldn't load the exam data. Please check the `exam_result.json` file."
        )
        return

    results = search_exam_results(user_query)

    if results:
        response_messages = []
        for res in results:
            response_messages.append(
                f"<b>Year:</b> {res['year']}\n"
                f"<b>Division:</b> {res['division']}\n"
                f"<b>Roll No:</b> {res['RollNo']}\n"
                f"<b>Exam Location:</b> {res['ExamLocation']}\n"
                f"<b>Download:</b> <a href='{res['Download']}'>Click to Download</a>"
            )
        
        # Join messages, ensuring not to exceed Telegram's message length limit (4096 characters)
        # If too many results, send them in multiple messages or truncate
        full_response = "\n\n---\n\n".join(response_messages)
        
        if len(full_response) > 4000: # Approximate limit
            await update.message.reply_text(
                "Found many results. Here are the first few:\n\n" + full_response[:3800] + "...",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text(
                f"Found {len(results)} result(s):\n\n{full_response}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(
            f"No results found for '{user_query}'. Please try a different query."
        )

def main() -> None:
    """Start the bot."""
    # Load data when the bot starts
    load_exam_data(JSON_FILE_PATH)

    # Create the Application and pass your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # On different commands - add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # On non-command messages - handle the message with the search function
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
