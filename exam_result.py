import json
import logging
from telegram import Update, ForceReply, InputFile # Import InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import io # For handling binary data in memory
import requests # Ensure requests is imported
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set. Please set it before running the bot.")
    exit(1) # Exit if token is not set
JSON_FILE_PATH = "all_regions_detailed_data.json"
REGIONS_JSON_FILE_PATH = "regions.json" # New: Path to regions.json

# Global variables to store data
EXAM_DATA = {} # Stores the structured exam results by year
REGION_LINK_MAP = {} # Maps region name to its original detail URL (for Referer header)

def load_exam_data(file_path, regions_file_path):
    """Loads the exam data from the JSON files."""
    global EXAM_DATA, REGION_LINK_MAP
    
    # Load all_regions_detailed_data.json
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            EXAM_DATA = json.load(f)
        
        loaded_years = ", ".join(EXAM_DATA.keys()) if EXAM_DATA else "None"
        total_entries_count = sum(len(v) for v in EXAM_DATA.values())
        logger.info(f"Successfully loaded exam data from {file_path}. Years found: [{loaded_years}]. Total entries: {total_entries_count}")
        
    except FileNotFoundError:
        logger.error(f"Error: Exam data JSON file not found at {file_path}")
        EXAM_DATA = {}
    except json.JSONDecodeError:
        logger.error(f"Error: Could not decode JSON from {file_path}. Check file format.")
        EXAM_DATA = {}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading exam data JSON: {e}")
        EXAM_DATA = {}

    # Load regions.json to build the Referer link map
    try:
        with open(regions_file_path, 'r', encoding='utf-8') as f:
            regions_data = json.load(f)
            REGION_LINK_MAP = {region['region_name']: region['link'] for region in regions_data}
        logger.info(f"Successfully loaded region links from {regions_file_path}. Total regions: {len(REGION_LINK_MAP)}")
    except FileNotFoundError:
        logger.error(f"Error: Regions JSON file not found at {regions_file_path}")
        REGION_LINK_MAP = {}
    except json.JSONDecodeError:
        logger.error(f"Error: Could not decode JSON from {regions_file_path}. Check file format.")
        REGION_LINK_MAP = {}
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading regions JSON: {e}")
        REGION_LINK_MAP = {}


def search_exam_results(query: str, year_filter: str = None):
    """
    Searches the loaded exam data for results matching the query.
    The search is case-insensitive and looks for matches in region, district,
    township, exam_center, and alphabet_code.
    Optionally filters by year.
    """
    if not EXAM_DATA:
        return []

    query_lower = query.lower()
    found_results = []

    for year, entries_for_year in EXAM_DATA.items():
        if year_filter and year_filter != year:
            continue

        for entry in entries_for_year:
            region = entry.get("region", "")
            district = entry.get("district", "")
            township = entry.get("township", "")
            exam_center = entry.get("exam_center", "")
            alphabet_code = entry.get("alphabet_code", "")
            download_link = entry.get("download_link", "N/A")
            entry_year = year

            if (query_lower in region.lower() or
                query_lower in district.lower() or
                query_lower in township.lower() or
                query_lower in exam_center.lower() or
                query_lower in alphabet_code.lower()):

                found_results.append({
                    "year": entry_year,
                    "region": region,
                    "district": district,
                    "township": township,
                    "exam_center": exam_center,
                    "alphabet_code": alphabet_code,
                    "download_link": download_link # Keep the download link here
                })
    return found_results

# --- Telegram Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your Exam Result Bot.\n\n"
        "Send me a Region, District, Township, Exam Center name, or Alphabet Code to find results. "
        "You can also specify a year, e.g., '2025 ရန်ကုန်တိုင်းဒေသကြီး'. "
        "For example: 'တောင်ကြီး', 'ရတက', 'ရန်ကုန်တိုင်းဒေသကြီး', or '2025 ရန်ကုန်တိုင်းဒေသကြီး'.",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /help is issued."""
    await update.message.reply_text(
        "Send me a Region, District, Township, Exam Center name, or Alphabet Code to find results. "
        "You can also specify a year at the beginning of your query, e.g., '2025 ရန်ကုန်တိုင်းဒေသကြီး'. "
        "I will search for matches and send the relevant PDF if available."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text messages and searches for exam results."""
    user_query = update.message.text.strip()
    logger.info(f"User {update.effective_user.id} ({update.effective_user.first_name}) searched for: {user_query}")

    if not EXAM_DATA:
        await update.message.reply_text(
            "I'm sorry, I couldn't load the exam data. Please ensure `all_regions_detailed_data.json` exists and is valid."
        )
        return

    year_filter = None
    parsed_query = user_query.split(maxsplit=1)

    if len(parsed_query) > 1 and parsed_query[0].isdigit() and len(parsed_query[0]) == 4:
        potential_year = parsed_query[0]
        if potential_year in EXAM_DATA:
            year_filter = potential_year
            actual_query = parsed_query[1]
            logger.info(f"Detected year filter: {year_filter}, Actual query: {actual_query}")
        else:
            actual_query = user_query
            await update.message.reply_text(f"No data found for year '{potential_year}'. Searching across all years for '{user_query}'.")
    else:
        actual_query = user_query

    results = search_exam_results(actual_query, year_filter)

    if results:
        # We will send each result as a separate message/file
        await update.message.reply_text(f"Found {len(results)} result(s). Attempting to send PDFs...")

        for i, res in enumerate(results):
            region_name = res['region']
            download_url = res['download_link']
            
            # --- Prepare Referer Header ---
            # Default to main page if specific region link not found (less ideal but fallback)
            referer_url = REGION_LINK_MAP.get(region_name, "https://www.myanmarexam.org/")

            if download_url == 'N/A' or download_url.endswith('.pdf') is False:
                message = (
                    f"<b>Result {i+1}:</b>\n"
                    f"<b>Year:</b> {res['year']}\n"
                    f"<b>Region:</b> {res['region']}\n"
                    f"<b>District:</b> {res['district']}\n"
                    f"<b>Township:</b> {res['township']}\n"
                    f"<b>Exam Center:</b> {res['exam_center']}\n"
                    f"<b>Alphabet Code:</b> {res['alphabet_code']}\n"
                    f"Download link not available or invalid: {download_url}"
                )
                await update.message.reply_html(message)
                continue # Move to next result

            # --- Download the PDF with Referer ---
            try:
                logger.info(f"Attempting to download {download_url} with Referer: {referer_url}")
                headers = {'Referer': referer_url, 'User-Agent': 'Mozilla/5.0'} # Added User-Agent for better mimicry
                pdf_response = requests.get(download_url, headers=headers, stream=True, timeout=30)
                pdf_response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

                # --- Send PDF to user ---
                # Create a file-like object from the downloaded content
                pdf_file = io.BytesIO(pdf_response.content)
                
                # Construct a descriptive filename
                filename = f"{res['region']}_{res['district']}_{res['township']}_{res['exam_center']}_{res['alphabet_code']}_{res['year']}.pdf"
                
                # Trim filename if too long for Telegram (max 255 chars)
                if len(filename) > 250:
                    filename = f"{res['region']}_{res['alphabet_code']}_{res['year']}.pdf"
                    if len(filename) > 250: # Even shorter if needed
                        filename = f"ExamResult_{res['year']}.pdf"

                # Send the document
                await update.message.reply_document(
                    document=InputFile(pdf_file, filename=filename),
                    caption=(
                        f"<b>Result {i+1}:</b>\n"
                        f"<b>Year:</b> {res['year']}\n"
                        f"<b>Region:</b> {res['region']}\n"
                        f"<b>District:</b> {res['district']}\n"
                        f"<b>Township:</b> {res['township']}\n"
                        f"<b>Exam Center:</b> {res['exam_center']}\n"
                        f"<b>Alphabet Code:</b> {res['alphabet_code']}" # FIXED: Removed extra </b>
                    ),
                    parse_mode='HTML'
                )
                logger.info(f"Sent PDF for {res['region']} - {res['exam_center']}")

            except requests.exceptions.RequestException as e:
                error_message = f"Failed to download PDF for {res['region']} ({res['exam_center']}). Error: {e}"
                logger.error(error_message)
                await update.message.reply_text(f"Could not download PDF for: {res['region']} - {res['exam_center']}. Error: {e}")
            except Exception as e:
                error_message = f"An unexpected error occurred while processing PDF for {res['region']} ({res['exam_center']}). Error: {e}"
                logger.error(error_message)
                await update.message.reply_text(f"An error occurred while sending PDF for: {res['region']} - {res['exam_center']}. Error: {e}")

    else:
        await update.message.reply_text(
            f"No results found for '{user_query}'. Please try a different query."
        )

def main() -> None:
    """Start the bot."""
    # Load data when the bot starts
    load_exam_data(JSON_FILE_PATH, REGIONS_JSON_FILE_PATH)

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
