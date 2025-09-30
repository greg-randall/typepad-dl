import os
import logging
import time
import sys
import threading
import concurrent.futures
import argparse
import re
from urllib.parse import urljoin, urlparse
from curl_cffi import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# --- Configuration ---
# The file containing the list of post URLs to download.
PERMALINKS_FILE = "permalinks.txt"
# The file to log which posts have been successfully downloaded.
DOWNLOADED_LOG_FILE = "downloaded_permalinks.txt"
# The main directory where all downloaded posts and media will be stored.
POSTS_DIR = "posts"
# Directory for shared assets (CSS, JS, fonts, etc.)
ASSETS_DIR = "posts/assets"
# Retry logic for fetching files
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds
# The browser profile to impersonate to avoid being blocked.
IMPERSONATE_BROWSER = "chrome110"

# Global debug flag
DEBUG_MODE = False

# --- Setup Logging ---
# Configures basic logging to print progress and error messages to the console.
# Set format to a simpler one to avoid clutter with the tqdm bar.
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def debug_print(message):
    """Print debug messages if debug mode is enabled"""
    if DEBUG_MODE:
        tqdm.write(f"DEBUG: {message}")

def setup_environment():
    """
    Creates the main 'posts' directory and assets subdirectory if they don't already exist.
    """
    if not os.path.exists(POSTS_DIR):
        os.makedirs(POSTS_DIR)
        logging.info(f"Created main directory: {POSTS_DIR}")
    
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR)
        logging.info(f"Created assets directory: {ASSETS_DIR}")

def get_asset_filename_from_url(asset_url):
    """
    Generates a safe filename for an asset from its URL.
    Handles query parameters and creates a unique but readable filename.
    """
    parsed = urlparse(asset_url)
    
    # Start with the basename
    filename = os.path.basename(parsed.path)
    
    # If no filename from path, use the last part of the domain + path
    if not filename or filename == '/':
        parts = [part for part in parsed.path.split('/') if part]
        if parts:
            filename = '_'.join(parts[-2:]) if len(parts) > 1 else parts[-1]
        else:
            filename = parsed.netloc.replace('.', '_')
    
    # If there are query parameters, add a hash to make it unique
    if parsed.query:
        import hashlib
        query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{query_hash}{ext}"
    
    # Clean up the filename
    filename = re.sub(r'[^\w\-_.]', '_', filename)
    
    return filename

def download_and_rewrite_css_imports(session, css_url, css_content, assets_dir, auth=None):
    """
    Downloads CSS and recursively downloads any @import or url() references.
    Returns modified CSS content with rewritten URLs.
    """
    debug_print(f"Processing CSS imports and url() references in: {css_url}")
    
    import_pattern = r'@import\s+(?:url\()?[\'"]?([^\'"\)]+)[\'"]?\)?[^;]*;'
    imports = re.findall(import_pattern, css_content)
    url_pattern = r'url\([\'"]?([^\'"\)]+)[\'"]?\)'
    urls = re.findall(url_pattern, css_content)
    all_assets = set(imports + urls)
    modified_css = css_content
    
    for asset_url in all_assets:
        try:
            full_asset_url = urljoin(css_url, asset_url)
            asset_filename = get_asset_filename_from_url(full_asset_url)
            asset_save_path = os.path.join(assets_dir, asset_filename)
            
            if not os.path.exists(asset_save_path):
                success = download_file(session, full_asset_url, asset_save_path, auth=auth)
                if not success:
                    continue
            
            relative_path = f"./{asset_filename}"
            modified_css = re.sub(
                f'@import\\s+(?:url\\()?[\'"]?{re.escape(asset_url)}[\'"]?\\)?',
                f'@import url("{relative_path}")', modified_css)
            modified_css = re.sub(
                f'url\\([\'"]?{re.escape(asset_url)}[\'"]?\\)',
                f'url("{relative_path}")', modified_css)
        except Exception as e:
            debug_print(f"Error processing CSS asset {asset_url}: {e}")
    
    return modified_css

def download_page_assets(session, html_content, base_url, assets_dir, auth=None):
    """
    Downloads all CSS, JS, fonts and other assets referenced in the HTML.
    Returns modified HTML with rewritten asset URLs.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    assets_downloaded = {}
    
    css_links = soup.find_all('link', rel='stylesheet') + soup.find_all('link', type='text/css')
    for css_link in css_links:
        href = css_link.get('href')
        if href:
            try:
                full_url = urljoin(base_url, href)
                filename = get_asset_filename_from_url(full_url)
                save_path = os.path.join(assets_dir, filename)
                if not os.path.exists(save_path):
                    response = session.get(full_url, impersonate=IMPERSONATE_BROWSER, timeout=5, auth=auth)
                    if response.status_code == 200:
                        modified_css = download_and_rewrite_css_imports(
                            session, full_url, response.text, assets_dir, auth)
                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(modified_css)
                        assets_downloaded[href] = filename
                else:
                    assets_downloaded[href] = filename
            except Exception as e:
                debug_print(f"Error downloading CSS {href}: {e}")
    
    js_scripts = soup.find_all('script', src=True)
    for js_script in js_scripts:
        src = js_script.get('src')
        if src:
            try:
                full_url = urljoin(base_url, src)
                filename = get_asset_filename_from_url(full_url)
                save_path = os.path.join(assets_dir, filename)
                if not os.path.exists(save_path):
                    if download_file(session, full_url, save_path, auth=auth):
                        assets_downloaded[src] = filename
                else:
                    assets_downloaded[src] = filename
            except Exception as e:
                debug_print(f"Error downloading JS {src}: {e}")

    icon_links = soup.find_all('link', rel=['icon', 'shortcut icon', 'apple-touch-icon'])
    for icon_link in icon_links:
        href = icon_link.get('href')
        if href:
            try:
                full_url = urljoin(base_url, href)
                filename = get_asset_filename_from_url(full_url)
                save_path = os.path.join(assets_dir, filename)
                if not os.path.exists(save_path):
                    if download_file(session, full_url, save_path, auth=auth):
                        assets_downloaded[href] = filename
                else:
                    assets_downloaded[href] = filename
            except Exception as e:
                debug_print(f"Error downloading icon {href}: {e}")
    
    for original_url, local_filename in assets_downloaded.items():
        relative_path = f"assets/{local_filename}"
        for tag in soup.find_all(['link', 'script'], href=original_url):
            tag['href'] = relative_path
        for tag in soup.find_all(['link', 'script'], src=original_url):
            tag['src'] = relative_path

    return str(soup)

def get_post_urls():
    if not os.path.exists(PERMALINKS_FILE):
        logging.error(f"Error: The file '{PERMALINKS_FILE}' was not found.")
        return []
    with open(PERMALINKS_FILE, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def get_already_downloaded_urls():
    downloaded = set()
    if os.path.exists(DOWNLOADED_LOG_FILE):
        with open(DOWNLOADED_LOG_FILE, 'r') as f:
            for line in f:
                downloaded.add(line.strip())
    return downloaded

def log_url_as_downloaded(url, lock):
    with lock:
        with open(DOWNLOADED_LOG_FILE, 'a') as f:
            f.write(url + '\n')

def generate_filename_from_url(url, blog_base_url, post_index):
    """
    Generates a filename from a URL. It tries to find a YYYY/MM date in the
    path and uses a sequential index to create a YYYY_MM_####_slug.html filename.
    """
    parsed_url = urlparse(url)
    path = parsed_url.path
    slug = os.path.splitext(os.path.basename(path))[0]
    date_match = re.search(r'/(\d{4})/(\d{2})/', path)

    # Convert the index to a zero-padded string (e.g., 9 becomes "0009")
    # Using 4 digits allows for up to 9,999 posts.
    order_prefix = str(post_index).zfill(4)

    if date_match:
        year = date_match.group(1)
        month = date_match.group(2)
        return f"{year}_{month}_{order_prefix}_{slug}"
    else:
        return f"{order_prefix}_{slug}"

def get_file_extension_from_content_type(content_type):
    content_type_map = {
        'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
        'image/gif': '.gif', 'image/webp': '.webp', 'image/svg+xml': '.svg',
        'image/bmp': '.bmp', 'image/tiff': '.tiff', 'application/pdf': '.pdf',
    }
    if content_type:
        content_type = content_type.split(';')[0].strip().lower()
        return content_type_map.get(content_type)
    return None

def detect_file_extension_from_content(content):
    if not content or len(content) < 8: return None
    if content.startswith(b'\xff\xd8\xff'): return '.jpg'
    if content.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if content.startswith(b'GIF87a') or content.startswith(b'GIF89a'): return '.gif'
    if content.startswith(b'RIFF') and b'WEBP' in content[:12]: return '.webp'
    return None

def download_file(session, url, save_path, fail_fast_on_500=False, auth=None):
    for attempt in range(MAX_RETRIES):
        try:
            extension = None
            try:
                head_response = session.head(url, impersonate=IMPERSONATE_BROWSER, timeout=5, auth=auth)
                if head_response.status_code == 200:
                    content_type = head_response.headers.get('Content-Type', '')
                    extension = get_file_extension_from_content_type(content_type)
                elif head_response.status_code == 404:
                    return False
            except Exception:
                pass
            
            response = session.get(url, impersonate=IMPERSONATE_BROWSER, timeout=5, auth=auth)
            if response.status_code == 200:
                if not extension:
                    extension = detect_file_extension_from_content(response.content)
                final_save_path = save_path
                if extension and not os.path.splitext(save_path)[1]:
                    final_save_path = save_path + extension
                with open(final_save_path, 'wb') as f:
                    f.write(response.content)
                return True

            if response.status_code >= 500 and response.status_code < 600 and fail_fast_on_500:
                debug_print(f"Got status {response.status_code} for {url}. Failing fast to try fallback.")
                return False
            elif response.status_code == 404:
                return False
            else:
                if DEBUG_MODE:
                    tqdm.write(f"WARNING: Got status {response.status_code} for {url} on attempt {attempt + 1}. Retrying...")
        except Exception as e:
            if DEBUG_MODE:
                tqdm.write(f"WARNING: Exception for {url} on attempt {attempt + 1}: {e}. Retrying...")
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    
    tqdm.write(f"ERROR: Failed to download {url} after {MAX_RETRIES} attempts.")
    return False

def process_url(post_index, url, blog_base_url, blog_name, session, lock, sleep_time, auth=None):
    stats = {"posts_processed": 0, "media_downloaded": 0, "media_failed": 0}
    blog_domain = urlparse(blog_base_url).netloc
    
    base_filename = generate_filename_from_url(url, blog_base_url, post_index)
    html_filename = os.path.splitext(base_filename)[0] + ".html"
    html_save_path = os.path.join(POSTS_DIR, html_filename)

    html_content = None
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, impersonate=IMPERSONATE_BROWSER, timeout=5, auth=auth)
            if response.status_code == 200:
                html_content = response.text
                break
            elif response.status_code == 404:
                tqdm.write(f"WARNING: Post not found (404) at {url}. Skipping.")
                return stats
            else:
                if DEBUG_MODE:
                    tqdm.write(f"WARNING: Got status {response.status_code} for {url} on attempt {attempt + 1}. Retrying...")
        except Exception as e:
            if DEBUG_MODE:
                tqdm.write(f"WARNING: Exception for {url} on attempt {attempt + 1}: {e}. Retrying...")
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    if html_content is None:
        tqdm.write(f"ERROR: Failed to fetch post HTML for {url} after {MAX_RETRIES} attempts. Skipping post.")
        return stats
    
    stats["posts_processed"] = 1
    
    with open(html_save_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    try:
        modified_html = download_page_assets(session, html_content, url, ASSETS_DIR, auth)
        with open(html_save_path, 'w', encoding='utf-8') as f:
            f.write(modified_html)
    except Exception:
        modified_html = html_content

    soup = BeautifulSoup(modified_html, 'html.parser')
    content_div = soup.find('div', class_='entry-content') or soup.find('article') or soup.find('body')

    if content_div:
        media_dir_name = os.path.splitext(base_filename)[0]
        media_dir_path = os.path.join(POSTS_DIR, media_dir_name)
        
        all_media_tags = content_div.find_all(['img', 'a'])
        if any(tag.get('src') or '.typepad.com/.a/' in tag.get('href', '') for tag in all_media_tags):
             if not os.path.exists(media_dir_path):
                os.makedirs(media_dir_path)

        for i, tag in enumerate(all_media_tags):
            is_image = tag.name == 'img'
            url_attr = 'src' if is_image else 'href'
            link = tag.get(url_attr, '')

            if not link:
                continue
            
            original_full_url = urljoin(url, link)

            # --- MODIFIED LOGIC ---
            if is_image:
                # For images, only download if they are from the same domain as the blog
                if blog_domain not in original_full_url:
                    debug_print(f"Skipping external image: {original_full_url}")
                    continue
            else: # This is an <a> tag
                is_typepad_media_link = '.typepad.com/.a/' in original_full_url
                is_direct_file_on_domain = blog_domain in original_full_url and blog_name in original_full_url
                
                # A link is a candidate if it's a special media link OR a direct file on our specific blog
                if not (is_typepad_media_link or is_direct_file_on_domain):
                    debug_print(f"Skipping external or irrelevant link: {original_full_url}")
                    continue

                # Now, block links that are just other web pages
                path = urlparse(original_full_url).path.lower()
                if path.endswith(('.html', '.htm')) or path == '' or path.endswith('/'):
                    continue
            # --- END MODIFIED LOGIC ---

            media_filename = os.path.basename(urlparse(original_full_url).path)
            if not media_filename: media_filename = f"media_{i}"
            
            media_save_path = os.path.join(media_dir_path, media_filename)
            if os.path.exists(media_save_path):
                continue

            urls_to_try = []
            if is_image and '.typepad.com/' in link:
                cleaned_link = re.sub(r'-\d+wi$', '', link)
                cleaned_full_url = urljoin(url, cleaned_link)
                if cleaned_full_url != original_full_url:
                    urls_to_try.append(cleaned_full_url)
            urls_to_try.append(original_full_url)

            success = False
            if len(urls_to_try) > 1:
                success = download_file(session, urls_to_try[0], media_save_path, fail_fast_on_500=True, auth=auth)

            if not success:
                success = download_file(session, urls_to_try[-1], media_save_path, auth=auth)
            
            if success:
                stats["media_downloaded"] += 1
            else:
                stats["media_failed"] += 1
                tqdm.write(f"ERROR: All download attempts failed for media: {link}")
    
    log_url_as_downloaded(url, lock)
    
    # Sleep AFTER all work for this URL is done.
    if sleep_time > 0:
        time.sleep(sleep_time)
        
    return stats

def main():
    global DEBUG_MODE
    parser = argparse.ArgumentParser(description="Download all posts and their media from a Typepad-style blog.")
    parser.add_argument("blog_url", help="The root URL of the blog (e.g., 'https://growabrain.typepad.com/growabrain/')")
    parser.add_argument("--threads", type=int, default=4, help="Number of concurrent download threads (default: 4).")
    parser.add_argument("--sleep-time", type=float, default=0.5, help="Seconds for a worker to sleep after finishing a post (default: 0.5).")
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("--username", help="Username for HTTP Basic Authentication (if required)")
    parser.add_argument("--password", help="Password for HTTP Basic Authentication (if required)")
    args = parser.parse_args()
    DEBUG_MODE = args.debug

    parsed_url = urlparse(args.blog_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        logging.error("Invalid URL provided. Please include the scheme (e.g., 'https://').")
        return

    path_parts = [part for part in parsed_url.path.split('/') if part]
    blog_name = path_parts[0] if path_parts else parsed_url.netloc.split('.')[0]
    BLOG_BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}/{blog_name}/"
    logging.info(f"Using Blog Base URL: {BLOG_BASE_URL}")

    setup_environment()
    all_post_urls_raw = get_post_urls()

    # --- Deduplicate URLs while preserving order ---
    seen_urls = set()
    unique_ordered_urls = []
    for url in all_post_urls_raw:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_ordered_urls.append(url)
    
    total_unique_urls = len(unique_ordered_urls)
    logging.info(f"Found {len(all_post_urls_raw)} total URLs in permalinks.txt, with {total_unique_urls} unique URLs.")
    # --- End Deduplication ---

    downloaded_urls = get_already_downloaded_urls()
    
    # Create a dictionary of URLs to process with their original index from the unique list
    urls_to_process_with_index = {
        url: i for i, url in enumerate(unique_ordered_urls) if url not in downloaded_urls
    }
    
    if not urls_to_process_with_index:
        logging.info("All posts have already been downloaded. Exiting.")
        return

    logging.info(f"{len(downloaded_urls)} posts already downloaded.")
    logging.info(f"Starting download of {len(urls_to_process_with_index)} new posts using {args.threads} workers.")
    
    session = requests.Session()
    file_lock = threading.Lock()

    # Setup authentication if provided
    auth = None
    if args.username and args.password:
        auth = (args.username, args.password)
        logging.info("Using HTTP Basic Authentication")

    total_stats = {"posts_processed": 0, "media_downloaded": 0, "media_failed": 0}

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            # Submit all tasks to the executor at once.
            future_to_url = {
                executor.submit(process_url, i, url, BLOG_BASE_URL, blog_name, session, file_lock, args.sleep_time, auth): url
                for url, i in urls_to_process_with_index.items()
            }
            
            # Process results as they are completed and show progress.
            completed_iterator = concurrent.futures.as_completed(future_to_url)
            for future in tqdm(completed_iterator, total=len(future_to_url), desc="Downloading Posts"):
                try:
                    result = future.result()
                    if result:
                        for key in total_stats:
                            total_stats[key] += result.get(key, 0)
                except Exception as exc:
                    url = future_to_url[future]
                    tqdm.write(f"ERROR: {url} generated an exception: {exc}")
        
        logging.info("--- All posts processed successfully. ---")

    except KeyboardInterrupt:
        tqdm.write("\nProcess interrupted by user. Exiting.")
        sys.exit(0)
    finally:
        logging.info("--- Script finished. ---")
        print("\n--- Download Summary ---")
        print(f"✅ Posts processed: {total_stats['posts_processed']}")
        print(f"🖼️ Pieces of media downloaded: {total_stats['media_downloaded']}")
        if total_stats['media_failed'] > 0:
            print(f"❌ Pieces of media failed: {total_stats['media_failed']}")
        print("------------------------")

if __name__ == "__main__":
    main()