import os
import re
import time
import logging
import argparse
from urllib.parse import urlparse, urljoin
from curl_cffi import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# --- Configuration ---
# The range of pages you want to scrape.
START_PAGE = 1
# The directory where raw HTML files will be stored.
DATA_DIR = "raw-paged-data"
# The file to store all the extracted permalinks.
PERMALINKS_FILE = "permalinks.txt"
# The file to log which pages have been successfully scanned, for resuming progress.
SCANNED_FILE = "scanned.txt"
# The delay in seconds to wait before retrying a failed request.
RETRY_DELAY = 30
# The browser profile to impersonate to avoid being blocked.
IMPERSONATE_BROWSER = "chrome110"

# --- Logging will be configured in main() ---

def setup_environment():
    """
    Creates the necessary directory for storing raw HTML data if it doesn't already exist.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logging.info(f"Created directory: {DATA_DIR}")

def get_already_scanned_pages():
    """
    Reads the scanned.txt file to build a set of page numbers that have already been
    processed. This allows the script to resume from where it left off.
    Returns:
        A set of integers representing the page numbers already scanned.
    """
    scanned_pages = set()
    if os.path.exists(SCANNED_FILE):
        with open(SCANNED_FILE, 'r') as f:
            for line in f:
                # Safely convert each line to an integer.
                try:
                    scanned_pages.add(int(line.strip()))
                except ValueError:
                    # Use tqdm.write to avoid interfering with a progress bar if this runs mid-script
                    tqdm.write(f"WARNING: Could not parse line in {SCANNED_FILE}: {line.strip()}")
    return scanned_pages

def save_permalinks(links):
    """
    Appends a list of found permalinks to the permalinks.txt file.
    Args:
        links (list): A list of URL strings to save.
    """
    with open(PERMALINKS_FILE, 'a', encoding='utf-8') as f:
        for link in links:
            f.write(link + '\n')

def mark_page_as_scanned(page_number):
    """
    Appends a page number to the scanned.txt file to mark it as complete.
    Args:
        page_number (int): The page number that was successfully processed.
    """
    with open(SCANNED_FILE, 'a') as f:
        f.write(str(page_number) + '\n')

def extract_permalinks_default(html_content, page_url, blog_name):
    """
    The default method. Uses BeautifulSoup to parse the HTML, find all links
    with the exact text "Permalink", and returns their href attributes.
    Args:
        html_content (str): The raw HTML of a webpage.
        page_url (str): The URL of the page being scanned, used to resolve relative links.
        blog_name (str): The name of the blog, used to construct the permalink prefix.
    Returns:
        A set of unique permalink URLs found on the page.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    permalinks = set()
    parsed_url = urlparse(page_url)
    permalink_prefix = f"{parsed_url.scheme}://{parsed_url.netloc}/{blog_name}/"

    for link in soup.find_all('a', href=True):
        if link.get_text(strip=True) == 'Permalink':
            href = link['href']
            # Join URL to handle relative links, then check prefix
            absolute_url = urljoin(page_url, href)
            if absolute_url.startswith(permalink_prefix):
                permalinks.add(absolute_url)

    return permalinks

def extract_permalinks_alternative(html_content, page_url, blog_name=None):
    """
    An alternative method. Uses a flexible regular expression to find links that match a
    common blog post URL structure (e.g., /YYYY/MM/post-title.html). It will find links
    from any domain on the page that match the pattern.
    Args:
        html_content (str): The raw HTML of a webpage.
        page_url (str): The URL of the page being scanned, used to resolve relative links.
        blog_name (str, optional): The name of the blog. Not used in this method. Defaults to None.
    Returns:
        A set of unique permalink URLs found on the page.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    permalinks = set()

    # This regex is flexible and looks for any path with a /YYYY/MM/ structure.
    post_pattern = re.compile(r'/\d{4}/\d{2}/[^/]+\.html')

    for link in soup.find_all('a', href=True):
        href = link['href']
        # Search for the pattern in the link
        if post_pattern.search(href):
            # Resolve relative URLs (e.g., "/2024/01/post.html") into full URLs
            absolute_url = urljoin(page_url, href)
            permalinks.add(absolute_url)

    return permalinks

def check_for_next_page(html_content, current_page_num):
    """
    Parses the HTML to find a valid 'Next' page link.
    A valid link is identified by being in the 'pager-right' section and
    containing either the text 'Next' or the '»' character. It must also
    point to the next sequential page.
    Args:
        html_content (str): The raw HTML of the current page.
        current_page_num (int): The number of the page just scraped.
    Returns:
        bool: True if a valid next page exists, False otherwise.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    next_link = soup.select_one('div.pager-inner span.pager-right a')

    if not next_link:
        logging.debug("CheckNextPage: Did not find a 'Next' link element using the selector.")
        return False

    link_text = next_link.get_text(strip=True).lower()
    if 'next' not in link_text and '»' not in link_text:
        logging.debug(f"CheckNextPage: Link text '{link_text}' does not contain 'next' or '»'.")
        return False

    next_href = next_link.get('href')
    if not next_href:
        logging.debug("CheckNextPage: 'Next' link found, but it has no href attribute.")
        return False

    match = re.search(r'/page/(\d+)/?$', next_href)
    if not match:
        logging.debug(f"CheckNextPage: Could not find page number in href '{next_href}'.")
        tqdm.write(f"WARNING: Found 'Next' link with an unexpected URL format: {next_href}")
        return False

    try:
        next_page_num = int(match.group(1))
        expected_next_page = current_page_num + 1

        if next_page_num == expected_next_page:
            logging.debug(f"CheckNextPage: Found valid 'Next' link to page {next_page_num}.")
            return True
        else:
            logging.debug(f"CheckNextPage: Sanity check fail. Current: {current_page_num}, Next link points to: {next_page_num}")
            tqdm.write(
                f"WARNING: Sanity check failed: Current page is {current_page_num}, but 'Next' link points to page {next_page_num}."
            )
            return False
    except (ValueError, IndexError):
        logging.debug(f"CheckNextPage: Failed to parse page number from '{next_href}'.")
        tqdm.write(f"WARNING: Could not parse page number from 'Next' link URL: {next_href}")
        return False

def main():
    """
    The main function to run the scraper.
    """
    parser = argparse.ArgumentParser(description="Scrape permalinks from a Typepad-style blog by iterating through its pages.")
    parser.add_argument("blog_url", help="The root URL of the blog (e.g., 'https://growabrain.typepad.com/growabrain/')")
    parser.add_argument(
        "--sleep-time",
        type=float,
        default=0.5,
        help="The delay in seconds between page requests. Default: 0.5"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for detailed output."
    )
    parser.add_argument(
        "--username",
        help="Username for HTTP Basic Authentication (if required)"
    )
    parser.add_argument(
        "--password",
        help="Password for HTTP Basic Authentication (if required)"
    )
    args = parser.parse_args()

    # --- Setup Logging ---
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    # --- Derive URLs from the input ---
    parsed_url = urlparse(args.blog_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        logging.error("Invalid URL provided. Please include the scheme (e.g., 'https://').")
        return

    path_parts = [part for part in parsed_url.path.split('/') if part]
    blog_name = path_parts[0] if path_parts else parsed_url.netloc.split('.')[0]

    BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}/{blog_name}/page/{{}}/"

    logging.info(f"Using Base URL for pages: {BASE_URL.format('<num>')}")
    logging.info(f"Using Blog Name: '{blog_name}'")

    setup_environment()
    scanned_pages = get_already_scanned_pages()
    logging.info(f"Found {len(scanned_pages)} already scanned pages. Resuming progress.")

    session = requests.Session()

    # Setup authentication if provided
    auth = None
    if args.username and args.password:
        auth = (args.username, args.password)
        logging.info("Using HTTP Basic Authentication")
    page_num = START_PAGE
    total_permalinks_found = 0

    with tqdm(unit=" page") as pbar:
        while True:
            pbar.set_description(f"Scanning Page {page_num}")

            if page_num in scanned_pages:
                page_num += 1
                continue

            url = BASE_URL.format(page_num)
            retries = 0
            max_retries = 5
            response_content = None

            while retries < max_retries:
                try:
                    logging.debug(f"Requesting URL: {url}")
                    response = session.get(url, impersonate=IMPERSONATE_BROWSER, timeout=20, auth=auth)
                    logging.debug(f"Received status code {response.status_code} for {url}")

                    if response.status_code == 200:
                        response_content = response.text
                        break
                    elif response.status_code == 404:
                        tqdm.write(f"Page {page_num} not found (404). Assuming this is the end of the blog.")
                        response_content = "STOP"
                        break
                    elif 500 <= response.status_code < 600:
                        tqdm.write(f"WARNING: Server error (status {response.status_code}) for page {page_num}. Retrying in {RETRY_DELAY}s...")
                        time.sleep(RETRY_DELAY)
                        retries += 1
                    else:
                        tqdm.write(f"ERROR: Unexpected status code {response.status_code} for page {page_num}. Skipping.")
                        response_content = "SKIP"
                        break

                except Exception as e:
                    tqdm.write(f"ERROR: Exception on page {page_num}: {e}. Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    retries += 1

            if response_content == "STOP":
                break
            if response_content == "SKIP" or response_content is None:
                if response_content is None:
                    tqdm.write(f"ERROR: Failed to fetch page {page_num} after {max_retries} retries. Skipping.")
                page_num += 1
                continue

            # --- Process successful fetch ---
            pbar.update(1)
            file_path = os.path.join(DATA_DIR, f'page_{page_num}.html')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response_content)

            # --- Permalink Extraction with Fallback Logic ---
            # Try the standard method first (looks for "Permalink" text).
            logging.debug(f"Using standard extraction method on page {page_num}.")
            permalinks = extract_permalinks_default(response_content, url, blog_name)

            # If the standard method finds nothing, fallback to the alternative method.
            if not permalinks:
                logging.debug(f"Standard method found no links. Trying alternative method as a fallback on page {page_num}.")
                permalinks = extract_permalinks_alternative(response_content, url, blog_name)

            # --- Save found permalinks ---
            if permalinks:
                logging.debug(f"Found {len(permalinks)} permalinks on page {page_num}.")
                save_permalinks(permalinks)
                total_permalinks_found += len(permalinks)
            else:
                logging.debug(f"No permalinks found on page {page_num} using any available method.")

            pbar.set_postfix(found=f"{total_permalinks_found} permalinks")
            mark_page_as_scanned(page_num)

            if not check_for_next_page(response_content, page_num):
                tqdm.write(f"No valid 'Next' link found on page {page_num}. Concluding scrape.")
                break

            page_num += 1
            time.sleep(args.sleep_time) # A small polite delay between pages

    logging.info(f"Scraping process complete. Found a total of {total_permalinks_found} permalinks.")

if __name__ == "__main__":
    main()